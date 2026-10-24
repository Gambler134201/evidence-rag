"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Version = {
  version_pk: number; version_id: string; version_no: number; status: string;
  effective_at: string; is_active: boolean; error_detail: string | null;
};
type Chunk = {
  chunk_id: number; ordinal: number; locator: {
    page?: number; para?: number; title_path?: string[];
  }; has_vector: boolean; preview: string;
};
type Job = { job_id: number; status: string; step: string | null; error_class: string | null; error_detail: string | null } | null;

type Detail = {
  document_id: number; kb_id: number; title: string; deactivated: boolean;
  active_version_id: number | null; active_build_status: string | null;
  versions: Version[]; chunks: Chunk[]; recent_jobs: Job[];
};

export default function DocumentDetail() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API_BASE}/documents/${params.id}`, { credentials: "include" });
    if (r.ok) setDetail(await r.json());
    else setMsg(`加载失败：${r.status}`);
  }, [params.id]);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [params.id]);

  async function publish(vid: number) {
    const r = await fetch(`${API_BASE}/versions/${vid}/publish`, {
      method: "POST", credentials: "include",
    });
    if (!r.ok) setMsg(`发布失败：${(await r.json()).detail ?? r.status}`);
    await load();
  }

  if (!detail) return <main className="page"><p>{msg ?? "加载中…"}</p></main>;

  return (
    <main className="page">
      <header className="header">
        <h1>{detail.title}</h1>
        <p className="tagline">
          <Link href="/kb">← 知识库管理</Link> ·{" "}
          {detail.deactivated
            ? <span className="badge warn">已停用</span>
            : <span className="badge ok">生效中</span>}{" "}
          · 构建状态：{detail.active_build_status ?? "未发布"}
        </p>
      </header>

      <section className="answer">
        <h2>版本（{detail.versions.length}）</h2>
        <table className="docs">
          <thead><tr><th>#</th><th>版本</th><th>状态</th><th>生效时间</th><th>当前</th><th></th></tr></thead>
          <tbody>
            {detail.versions.map(v => (
              <tr key={v.version_id}>
                <td>{v.version_no}</td>
                <td>{v.version_id}</td>
                <td>{v.status}{v.error_detail && <span className="err-detail"> · {v.error_detail}</span>}</td>
                <td>{new Date(v.effective_at).toLocaleString("zh-CN")}</td>
                <td>{v.is_active ? <span className="badge ok">当前版本</span> : ""}</td>
                <td>
                  {!v.is_active && v.status === "ready" && (
                    <button className="op" onClick={() => publish(v.version_pk)}>发布</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="answer">
        <h2>解析预览（{detail.chunks.length} 个片段）</h2>
        {detail.chunks.length === 0 && <p>暂无已发布的解析内容。</p>}
        <ol className="chunks">
          {detail.chunks.map(c => (
            <li key={c.chunk_id}>
              <span className="badge">{c.locator.title_path?.join(" / ") ?? (c.locator.page ? `第 ${c.locator.page} 页` : `第 ${c.locator.para} 段`)}</span>{" "}
              {!c.has_vector && <span className="badge warn">未向量化</span>}
              <p className="segment">{c.preview}…</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="answer">
        <h2>最近任务</h2>
        <ul className="chunks">
          {detail.recent_jobs?.map(j => j && (
            <li key={j.job_id}>
              #{j.job_id} · {j.status}{j.step ? ` · ${j.step}` : ""}
              {j.error_detail && <span className="err-detail"> · {j.error_class}: {j.error_detail}</span>}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
