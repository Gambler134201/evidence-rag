"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type ChunkView = {
  chunk_id: number; version_id: number;
  locator: { page?: number; para?: number; title_path?: string[] };
  content: string;
};

export default function ChunkOriginal() {
  const params = useParams<{ id: string }>();
  const [d, setD] = useState<ChunkView | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API_BASE}/chunks/${params.id}`, { credentials: "include" });
    if (!r.ok) { setMsg(`加载失败：${r.status}`); return; }
    setD(await r.json());
  }, [params.id]);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [params.id]);

  if (!d) return <main className="page"><p>{msg ?? "加载中…"}</p></main>;

  const where = d.locator.title_path?.join(" / ")
    ?? (d.locator.page ? `第 ${d.locator.page} 页` : `第 ${d.locator.para} 段`);

  return (
    <main className="page">
      <header className="header">
        <h1>原文片段</h1>
        <p className="tagline"><Link href="/runs">← 返回运行记录</Link> · 定位：{where}</p>
      </header>
      <section className="answer">
        <p className="segment">{d.content}</p>
      </section>
      <p className="runid">chunk {d.chunk_id} · version {d.version_id}</p>
    </main>
  );
}
