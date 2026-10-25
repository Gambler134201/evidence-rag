"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Run = {
  run_id: string; kb_id: number; question: string; status: string;
  error_class: string | null; total_ms: number | null; created_at: string;
};

const STATUS_CN: Record<string, string> = {
  answered: "已回答", insufficient_evidence: "证据不足", needs_clarification: "需澄清",
  conflicting_evidence: "证据冲突", knowledge_changed: "知识已变更", error: "错误",
};

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [total, setTotal] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API_BASE}/query-runs?limit=50`, { credentials: "include" });
    if (r.status === 401) { setMsg("请先在首页登录"); setRuns([]); return; }
    if (!r.ok) { setMsg(`加载失败：${r.status}`); return; }
    const body = await r.json();
    setRuns(body.runs);
    setTotal(body.total);
  }, []);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  return (
    <main className="page">
      <header className="header">
        <h1>运行记录</h1>
        <p className="tagline"><Link href="/">← 返回问答</Link> · 共 {total} 条（仅本人可见） · <button className="op" onClick={load}>刷新</button></p>
      </header>

      {msg && <p className="badge err">{msg}</p>}

      <section className="answer">
        {runs === null && <p>加载中…</p>}
        {runs !== null && (
          <>
            {runs.length === 0 && <p>暂无运行记录，去首页提一个问题。</p>}
            {runs.length > 0 && (
              <table className="docs">
                <thead><tr><th>时间</th><th>问题</th><th>状态</th><th>耗时</th><th>错误</th><th></th></tr></thead>
                <tbody>
                  {runs.map(x => (
                    <tr key={x.run_id}>
                      <td>{new Date(x.created_at).toLocaleString("zh-CN")}</td>
                      <td>{x.question}</td>
                      <td><span className={x.status === "answered" ? "badge ok" : "badge warn"}>
                        {STATUS_CN[x.status] ?? x.status}</span></td>
                      <td>{x.total_ms ? `${(x.total_ms / 1000).toFixed(1)}s` : "—"}</td>
                      <td>{x.error_class ? <span className="err-detail">{x.error_class}</span> : "—"}</td>
                      <td><Link href={`/runs/${x.run_id}`}>详情 →</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>
    </main>
  );
}
