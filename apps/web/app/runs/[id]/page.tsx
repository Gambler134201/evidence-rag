"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Evidence = {
  evidence_no: string; chunk_id: number; version_id: number;
  locator: { page?: number; para?: number; title_path?: string[] };
  score: number | null; content_preview: string;
};
type Trace = {
  run_id: string; kb_id: number; question: string; status: string;
  segments: { text: string; citation_ids: string[] }[] | null;
  error_class: string | null; error_detail: string | null;
  retrieval_ms: number | null; generation_ms: number | null; total_ms: number | null;
  prompt_tokens: number | null; completion_tokens: number | null;
  cost_note: string | null; config_snapshot: Record<string, unknown>;
  evidence: Evidence[];
};

export default function RunTrace() {
  const params = useParams<{ id: string }>();
  const [d, setD] = useState<Trace | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API_BASE}/query-runs/${params.id}`, { credentials: "include" });
    if (!r.ok) { setMsg(`加载失败：${r.status}`); return; }
    setD(await r.json());
  }, [params.id]);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [params.id]);

  if (!d) return <main className="page"><p>{msg ?? "加载中…"}</p></main>;

  return (
    <main className="page">
      <header className="header">
        <h1>运行轨迹</h1>
        <p className="tagline"><Link href="/runs">← 运行记录</Link> · {d.run_id}</p>
      </header>

      <section className="answer">
        <div className="answer-head">
          <span className={d.status === "answered" ? "badge ok" : "badge warn"}>
            {d.status}</span>
          {d.error_class && <span className="err-detail">{d.error_class}: {d.error_detail}</span>}
        </div>
        <p className="segment">问题：{d.question}</p>
        {d.segments?.map((s, i) => (
          <p key={i} className="segment">{s.text}{" "}
            {s.citation_ids?.map(cid => <sup key={cid} className="cite">{cid}</sup>)}</p>
        ))}
      </section>

      <section className="answer">
        <h2>检索与生成轨迹</h2>
        <table className="docs">
          <tbody>
            <tr><td>检索耗时</td><td>{d.retrieval_ms ?? "—"} ms</td></tr>
            <tr><td>生成耗时</td><td>{d.generation_ms ?? "—"} ms</td></tr>
            <tr><td>总耗时</td><td>{d.total_ms ?? "—"} ms</td></tr>
            <tr><td>Token（输入/输出）</td><td>{d.prompt_tokens ?? "未知"} / {d.completion_tokens ?? "未知"}</td></tr>
            <tr><td>费用</td><td>{d.cost_note ?? "未知（不填 0）"}</td></tr>
            <tr><td>检索模式</td><td>{String(d.config_snapshot?.retrieval ?? "—")}</td></tr>
            <tr><td>提示词版本</td><td>{String(d.config_snapshot?.prompt ?? "—")}</td></tr>
          </tbody>
        </table>
      </section>

      <section className="answer">
        <h2>证据（{d.evidence?.length ?? 0}）</h2>
        <ol className="chunks">
          {d.evidence?.map(e => (
            <li key={e.evidence_no}>
              <b>{e.evidence_no}</b> · 定位{" "}
              {e.locator.title_path?.join(" / ") ?? (e.locator.page ? `第 ${e.locator.page} 页` : `第 ${e.locator.para} 段`)}
              {e.score !== null && ` · 相似度 ${e.score}`} ·{" "}
              <Link href={`/chunks/${e.chunk_id}`}>查看原文片段 →</Link>
              <p className="segment">{e.content_preview}…</p>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
