"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type ChunkRow = {
  chunk_id: number; ordinal: number; is_hit: boolean;
  locator: { page?: number; para?: number; title_path?: string[] };
  content: string;
};
type Context = {
  document_id: number; title: string; version_id: number; hit_chunk_id: number;
  chunks: ChunkRow[];
};

export default function ChunkOriginal() {
  const params = useParams<{ id: string }>();
  const [d, setD] = useState<Context | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API_BASE}/chunks/${params.id}/context`, { credentials: "include" });
    if (!r.ok) {
      // 回退：上下文接口不可用时退回单片段视图
      const r2 = await fetch(`${API_BASE}/chunks/${params.id}`, { credentials: "include" });
      if (!r2.ok) { setMsg(`加载失败：${r2.status}`); return; }
      const one = await r2.json();
      setD({ document_id: 0, title: "原文片段", version_id: one.version_id,
             hit_chunk_id: one.chunk_id,
             chunks: [{ chunk_id: one.chunk_id, ordinal: 0, is_hit: true,
                        locator: one.locator, content: one.content }] });
      return;
    }
    setD(await r.json());
  }, [params.id]);

  useEffect(() => {
    load();
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [params.id]);

  useEffect(() => {
    if (d) document.getElementById("hit")?.scrollIntoView({ block: "center" });
  }, [d]);

  if (!d) return <main className="page"><p>{msg ?? "加载中…"}</p></main>;

  const hit = d.chunks.find(c => c.is_hit);
  const where = hit?.locator.title_path?.join(" / ")
    ?? (hit?.locator.page ? `第 ${hit.locator.page} 页` : "—");

  return (
    <main className="page">
      <header className="header">
        <h1>原文 · {d.title}</h1>
        <p className="tagline"><Link href="/runs">← 返回运行记录</Link> · 命中定位：{where} · 版本 {d.version_id}</p>
      </header>

      <section className="answer">
        <h2>全文（{d.chunks.length} 段，命中段已高亮）</h2>
        <div className="docview">
          {d.chunks.map(c => (
            <div key={c.chunk_id} id={c.is_hit ? "hit" : undefined}
                 className={"docchunk" + (c.is_hit ? " hithl" : "")}>
              <div className="docchunk-loc">
                {c.locator.title_path?.join(" / ") ?? (c.locator.page ? `第 ${c.locator.page} 页` : `第 ${c.locator.para} 段`)}
              </div>
              <p className="segment">{c.content}</p>
            </div>
          ))}
        </div>
      </section>
      <p className="runid">chunk {d.hit_chunk_id} · version {d.version_id}</p>
    </main>
  );
}
