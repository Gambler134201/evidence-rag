"use client";

import Link from "next/link";
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
  low_relevance?: boolean;
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
  const [needLogin, setNeedLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginMsg, setLoginMsg] = useState<string | null>(null);

  async function login() {
    setLoginMsg(null);
    try {
      const r = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      if (r.ok) {
        setNeedLogin(false);
        setLoginMsg(null);
      } else {
        setLoginMsg(`登录失败：${(await r.json()).detail ?? r.status}`);
      }
    } catch (e) {
      setLoginMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function ask() {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResp(null);
    try {
      const r = await fetch(`${API_BASE}/knowledge-bases/${KB_ID}/queries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ question, top_k: 5 }),
      });
      if (r.status === 401) {
        setNeedLogin(true);
        return;
      }
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
        <p className="tagline">回答基于当前有效文档，每个结论都可以点开原文核对。 <Link href="/kb">知识库管理 →</Link> · <Link href="/runs">运行记录 →</Link></p>
      </header>

      {needLogin && (
        <section className="login">
          <p>需要登录（本地演示账号，见 docs/worklog 创建说明）：</p>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 placeholder="密码" onKeyDown={(e) => e.key === "Enter" && login()} />
          <button onClick={login}>登录</button>
          {loginMsg && <p className="badge err">{loginMsg}</p>}
        </section>
      )}

      <section className="ask">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例如：A 团队验收期是几天？"
          rows={2}
        />
        <button onClick={ask} disabled={busy || !question.trim()}>
          {busy ? "查询中…" : "提问"}
        </button>
        {error && <p className="badge err">请求失败：{error}</p>}
      </section>

      {busy && (
        <section className="answer loading">
          <span className="spinner" />
          正在检索与生成…（本地模型约 5～25 秒）
        </section>
      )}

      {resp && (
        <section className="answer">
          <div className="answer-head">
            <span className={badge?.cls ?? "badge"}>{badge?.label ?? resp.status}</span>
            {resp.low_relevance && <span className="badge warn">证据相关度较低，建议补充条件或换个问法</span>}
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
                {resp.evidence.map((ev) => {
                  const maxScore = Math.max(...resp.evidence.map((x) => x.score), 1e-6);
                  const pct = Math.max(4, Math.round((ev.score / maxScore) * 100));
                  return (
                    <li key={ev.id}>
                      <div>
                        <b>{ev.id}</b> 《{ev.document_title}》 · {ev.version_label} ·{" "}
                        {locatorText(ev.locator)}
                      </div>
                      <div className="sim">
                        <span style={{ width: `${pct}%` }} />
                      </div>
                      <span className="sim-num">相对匹配度 {pct}%</span>
                    </li>
                  );
                })}
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
