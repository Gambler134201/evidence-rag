"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type FbRow = {
  feedback_id: number; run_id: string; question: string;
  run_status: string; useful: boolean; reason: string | null; created_at: string;
};

type Doc = {
  document_id: number;
  title: string;
  deactivated: boolean;
  active_version_id: number | null;
  active_version: string | null;
  active_build_status: string | null;
  total_chunks: number | null;
  publishable_version_ids: number[];
  latest_job: { job_id: number; status: string; step: string | null; error_class: string | null; error_detail: string | null } | null;
};

const JOB_CN: Record<string, string> = {
  queued: "排队中", running: "处理中", succeeded: "完成", failed: "失败", canceled: "已取消",
};
const BUILD_CN: Record<string, string> = {
  pending: "待处理", running: "处理中", ready: "就绪", failed: "失败",
};

export default function KbPage() {
  const [kbs, setKbs] = useState<{ id: number; name: string; slug: string }[]>([]);
  const [kbId, setKbId] = useState<number | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [autoPublish, setAutoPublish] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [needLogin, setNeedLogin] = useState(false);
  const [fbs, setFbs] = useState<FbRow[] | null>(null);

  const load = useCallback(async (id: number | null) => {
    const target = id ?? kbId;
    try {
      const k = await fetch(`${API_BASE}/knowledge-bases`, { credentials: "include" });
      if (k.status === 401) { setNeedLogin(true); return; }
      const kbs = await k.json();
      setKbs(kbs);
      const chosen = id ?? kbs[0]?.id ?? null;
      if (chosen) {
        setKbId(chosen);
        const d = await fetch(`${API_BASE}/knowledge-bases/${chosen}/documents`, { credentials: "include" });
        if (d.ok) setDocs(await d.json());
        const f = await fetch(`${API_BASE}/knowledge-bases/${chosen}/feedback`, { credentials: "include" });
        setFbs(f.ok ? await f.json() : null);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }, [kbId]);

  useEffect(() => { load(kbId); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const busy = docs.some(d => d.latest_job && ["queued", "running"].includes(d.latest_job.status));
  useEffect(() => {
    if (!busy || !kbId) return;
    const t = setInterval(() => load(kbId), 3000);
    return () => clearInterval(t);
  }, [busy, kbId, load]);

  async function upload() {
    if (!file || !kbId) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("auto_publish", String(autoPublish));
    const r = await fetch(`${API_BASE}/knowledge-bases/${kbId}/documents`, {
      method: "POST", credentials: "include", body: fd,
    });
    const body = await r.json();
    if (r.ok) {
      setMsg(body.duplicate_note ?? (body.job_id ? "已入队，处理中…" : "已复用现有索引"));
      setFile(null);
      await load(kbId);
    } else {
      setMsg(`上传失败：${body.detail ?? r.status}`);
      if (r.status === 401) setNeedLogin(true);
    }
  }

  async function act(url: string, method: string, form?: FormData) {
    const r = await fetch(`${API_BASE}${url}`, { method, credentials: "include", body: form });
    if (!r.ok) setMsg(`${method} 失败：${(await r.json()).detail ?? r.status}`);
    if (kbId) await load(kbId);
  }

  return (
    <main className="page">
      <header className="header">
        <h1>知识库管理</h1>
        <p className="tagline"><Link href="/">← 返回问答</Link> · 上传 → 处理 → 发布 → 停用，全程可追溯</p>
      </header>

      {needLogin && <p className="badge err">请先在首页登录</p>}

      <section className="ask">
        <select value={kbId ?? ""} onChange={e => load(Number(e.target.value))}>
          {kbs.map(k => <option key={k.id} value={k.id}>{k.name}（{k.slug}）</option>)}
        </select>
        <input type="file" accept=".md,.txt,.pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} />
        <label><input type="checkbox" checked={autoPublish}
                      onChange={e => setAutoPublish(e.target.checked)} /> 处理完成后自动发布</label>
        <button onClick={upload} disabled={!file || !kbId}>上传</button>
        <button onClick={() => kbId && load(kbId)}>刷新</button>
        {msg && <p className="badge">{msg}</p>}
      </section>

      <section className="answer">
        <table className="docs">
          <thead>
            <tr><th>文档</th><th>状态</th><th>当前版本</th><th>构建</th><th>片段</th><th>最新任务</th><th>操作</th></tr>
          </thead>
          <tbody>
            {docs.map(d => (
              <tr key={d.document_id}>
                <td><Link href={`/kb/documents/${d.document_id}`}>{d.title}</Link></td>
                <td>{d.deactivated ? <span className="badge warn">已停用</span> : <span className="badge ok">生效</span>}</td>
                <td>{d.active_version ?? "—"}</td>
                <td>{d.active_build_status ? (BUILD_CN[d.active_build_status] ?? d.active_build_status) : "—"}</td>
                <td>{d.total_chunks ?? "—"}</td>
                <td>
                  {d.latest_job ? (
                    <>
                      {JOB_CN[d.latest_job.status] ?? d.latest_job.status}
                      {d.latest_job.error_detail && (
                        <span className="err-detail"> · {d.latest_job.error_class}: {d.latest_job.error_detail}</span>
                      )}
                    </>
                  ) : "—"}
                </td>
                <td className="ops">
                  {d.publishable_version_ids.map(vid => (
                    <button key={vid} className="op"
                            onClick={() => act(`/versions/${vid}/publish`, "POST")}>
                      发布 v{vid}
                    </button>
                  ))}
                  <button className="op"
                          onClick={() => {
                            const fd = new FormData();
                            fd.append("active", String(!d.deactivated));
                            act(`/documents/${d.document_id}`, "PATCH", fd);
                          }}>
                    {d.deactivated ? "恢复" : "停用"}
                  </button>
                  {d.latest_job?.status === "failed" && (
                    <button className="op"
                            onClick={() => act(`/ingestion-jobs/${d.latest_job!.job_id}/retry`, "POST")}>
                      重试
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {docs.length === 0 && <p>暂无文档，先上传一份。</p>}
      </section>

      <section className="answer">
        <h2>反馈回流清单（无用反馈 → 评测候选）</h2>
        {fbs === null && <p>—</p>}
        {fbs?.length === 0 && <p>暂无反馈。</p>}
        {fbs?.length > 0 && (
          <table className="docs">
            <thead><tr><th>时间</th><th>问题</th><th>运行状态</th><th>原因</th><th></th></tr></thead>
            <tbody>
              {fbs.filter(x => !x.useful).map(x => (
                <tr key={x.feedback_id}>
                  <td>{new Date(x.created_at).toLocaleString("zh-CN")}</td>
                  <td>{x.question}</td>
                  <td>{x.run_status}</td>
                  <td>{x.reason ?? "—"}</td>
                  <td><Link href={`/runs/${x.run_id}`}>轨迹 →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
