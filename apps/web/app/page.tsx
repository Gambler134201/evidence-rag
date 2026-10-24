"use client";

import { useState } from "react";

type Evidence = {
  id: string;
  document_title: string;
  version_label: string;
  locator: { page?: number; para?: number; title_path?: string[] };
  score: number;
};

type Segment = { text: string; citation_ids: string[] };

type QueryResponse = {
  run_id: string;
  status: string;
  segments: Segment[];
  evidence: Evidence[];
  clarify?: string[];
  error_detail?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const KB_ID = process.env.NEXT_PUBLIC_KB_ID || "1";

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  answered: { label: "已回答", cls: "badge ok" },
  insufficient_evidence: { label: "证据不足，已拒答", cls: "badge warn" },
  needs_clarification: { label: "需要澄清", cls: "badge warn" },
  conflicting_evidence: { label: "证据冲突", cls: "badge warn" },
  knowledge_changed: { label: "知识已更新，请重新提问", cls: "badge warn" },
  error: { label: "服务错误（非“无答案”）", cls: "badge err" },
};

function locatorText(loc: Evidence["locator"]): string {
  if (loc.title_path?.length) return loc.title_path.join(" / ") + (loc.para ? ` · 第 ${loc.para} 段` : "");
  if (loc.page) return `第 ${loc.page} 页`;
  if (loc.para) return `第 ${loc.para} 段`;
  return "—";
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [resp, setResp] = useState<QueryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResp(null);
    try {
      const r = await fetch(`${API_BASE}/knowledge-bases/${KB_ID}/queries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: 5, local_user_id: 1 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setResp(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const badge = resp ? STATUS_BADGE[resp.status] : undefined;

  return (
    <main className="page">
      <header className="header">
        <h1>知据 <span className="en">evidence-rag</span></h1>
        <p className="tagline">回答基于当前有效文档，每个结论都可以点开原文核对。</p>
      </header>

      <section className="ask">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例如：A 团队验收期是几个工作日？"
          rows={2}
        />
        <button onClick={ask} disabled={busy || !question.trim()}>
          {busy ? "查询中…" : "提问"}
        </button>
        {error && <p className="badge err">请求失败：{error}</p>}
      </section>

      {resp && (
        <section className="answer">
          <div className="answer-head">
            <span className={badge?.cls ?? "badge"}>{badge?.label ?? resp.status}</span>
            {resp.error_detail && <code className="err-detail">{resp.error_detail}</code>}
          </div>

          {resp.segments?.map((seg, i) => (
            <p key={i} className="segment">
              {seg.text}{" "}
              {seg.citation_ids?.map((cid) => (
                <sup key={cid} className="cite">{cid}</sup>
              ))}
            </p>
          ))}

          {resp.clarify && resp.clarify.length > 0 && (
            <ul className="clarify">
              {resp.clarify.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          )}

          {resp.evidence?.length > 0 && (
            <details className="evidence" open>
              <summary>证据（{resp.evidence.length}）</summary>
              <ol>
                {resp.evidence.map((ev) => (
                  <li key={ev.id}>
                    <b>{ev.id}</b> 《{ev.document_title}》 · {ev.version_label} ·{" "}
                    {locatorText(ev.locator)} · 相似度 {ev.score}
                  </li>
                ))}
              </ol>
            </details>
          )}

          <p className="runid">运行记录 {resp.run_id}</p>
        </section>
      )}

      <footer className="footer">
        阶段 1 本地演示 · 仅使用合成资料 · 认证与权限在阶段 2 接入
      </footer>
    </main>
  );
}
