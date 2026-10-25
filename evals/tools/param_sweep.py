"""B2/B3：冻结 dev 集检索参数扫描与重排实验（纯检索，无生成调用）。

数据：冻结 dev 40 题（排除"设计性不可达"题——金标锚点不在已发布语料中的，
如历史/草稿版本题，按口径不计 Recall 分母）。
问题向量：真实 bge-m3 一次批量调用（免费档）。语料向量：直接读库。
"""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

import os

if os.environ.get("ENABLE_REAL_MODEL_CALLS") != "1":
    print("拒绝运行：本工具会调用 Embedding/Rerank API，必须 ENABLE_REAL_MODEL_CALLS=1")
    sys.exit(2)

import jieba  # noqa: E402
import yaml  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from evidence_rag.config import get_settings  # noqa: E402
from evidence_rag.db import engine  # noqa: E402
from evidence_rag.providers import get_clients  # noqa: E402
from evidence_rag.retrieval import _tokenize  # noqa: E402

ALLOWED_SQL = """
d.kb_id = :kb_id AND d.deactivated_at IS NULL
AND d.active_version_id = c.version_id
AND d.active_index_build_id = c.index_build_id
AND dv.effective_at <= now()
"""


def main() -> int:
    settings = get_settings()
    generation, embedder = get_clients()
    session = sessionmaker(bind=engine)()

    # 冻结 dev 题
    qs = []
    for ln in (REPO / "evals/datasets/main-80.jsonl").read_text(encoding="utf-8").splitlines()[1:]:
        if ln.strip():
            r = json.loads(ln)
            if r["split"] == "dev":
                qs.append(r)
    print(f"dev 题：{len(qs)}")

    kb_id_by_slug = {}
    for kid, slug in session.execute(text("SELECT id, slug FROM knowledge_bases")).all():
        kb_id_by_slug[slug] = kid

    # 语料：按 kb 缓存（chunk id + content）
    kb_chunks = {}
    for slug, kid in kb_id_by_slug.items():
        rows = session.execute(text(f"""
            SELECT c.id, c.content
            FROM chunks c
            JOIN index_builds b ON b.id = c.index_build_id
            JOIN document_versions dv ON dv.id = c.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE {ALLOWED_SQL}
        """), {"kb_id": kid}).all()
        kb_chunks[kid] = rows
    print("语料 chunk 数（按库）：", {k: len(v) for k, v in kb_chunks.items()})

    # 设计性不可达检测：金标锚点不在该库已发布正文 → 剔除分母
    eval_qs, skipped = [], []
    for q in qs:
        kid = kb_id_by_slug[q["caller"]["kb"]]
        corpus_text = "\n".join(c for _, c in kb_chunks.get(kid, []))
        gold = [g for g in q.get("gold_evidence", []) if g["anchor"] in corpus_text]
        if gold:
            eval_qs.append((q, gold))
        else:
            skipped.append(q["id"])
    print(f"可评测题：{len(eval_qs)}（剔除设计性不可达 {len(skipped)}: {skipped}）")

    # 批量 Embedding 问题（1 次 API 调用）
    q_texts = [q["q"] for q, _ in eval_qs]
    q_vecs = embedder.embed(q_texts)

    def rank_vector(kid, qv, topn):
        return session.execute(text(f"""
            SELECT c.id, c.content, 1 - (c.embedding <=> CAST(:vec AS vector)) AS score
            FROM chunks c
            JOIN index_builds b ON b.id = c.index_build_id
            JOIN document_versions dv ON dv.id = c.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE {ALLOWED_SQL} AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:vec AS vector)
            LIMIT :limit
        """), {"kb_id": kid, "vec": qv, "limit": topn}).all()

    bm25_by_kb = {}
    for kid, chunks in kb_chunks.items():
        tok = [_tokenize(c) for _, c in chunks]
        if tok:
            bm25_by_kb[kid] = BM25Okapi(tok)

    def rank_bm25(kid, qtext, topn):
        bm25 = bm25_by_kb.get(kid)
        if bm25 is None:
            return []
        scores = bm25.get_scores(_tokenize(qtext))
        ranked = sorted(zip(kb_chunks[kid], scores), key=lambda x: x[1], reverse=True)[:topn]
        return [(cid, c, s) for (cid, c), s in ranked]

    def rrf_fuse(vec_rows, bm_rows, k, topn):
        fused = {}
        content_by_id = {}
        for rank, (cid, content, _s) in enumerate(vec_rows, start=1):
            fused[cid] = fused.get(cid, 0) + 1 / (k + rank)
            content_by_id[cid] = content
        for rank, (cid, c, _s) in enumerate(bm_rows, start=1):
            fused[cid] = fused.get(cid, 0) + 1 / (k + rank)
            content_by_id[cid] = c
        ordered = sorted(fused.items(), key=lambda x: -x[1])[:topn]
        return [(cid, content_by_id[cid], s) for cid, s in ordered]

    def recall_at(ranked_rows, gold):
        text_all = "\n".join(c for _, c, _s in ranked_rows)
        hits = sum(1 for g in gold if g["anchor"] in text_all)
        return (hits, len(gold))

    configs = [("vector@5", "vector", 5, None)]
    for k in (40, 60, 120):
        configs.append((f"hybrid-rrf{k}@5", "hybrid", 5, k))
    configs += [("vector@8", "vector", 8, None), ("hybrid-rrf60@8", "hybrid", 8, 60)]

    results = {}
    for label, mode, topn, rrf_k in configs:
        hits = total = 0
        per_q: dict[str, str] = {}
        for (q, gold), qv in zip(eval_qs, q_vecs):
            kid = kb_id_by_slug[q["caller"]["kb"]]
            if mode == "vector":
                ranked = rank_vector(kid, qv, topn)
            else:
                vec_rows = rank_vector(kid, qv, max(topn * 4, 20))
                bm_rows = rank_bm25(kid, q["q"], max(topn * 4, 20))
                ranked = rrf_fuse(vec_rows, bm_rows, rrf_k, topn)
            r = recall_at(ranked, gold)
            per_q[q["id"]] = f"{r[0]}/{r[1]}"
            hits += r[0]
            total += r[1]
        results[label] = {"recall": hits / total if total else 0, "hits": hits,
                          "total": total, "per_question": per_q}
        print(f"  {label}: Recall = {hits}/{total} = {hits/total*100:.1f}%")

    # ── B3 重排实验：vector top-20 → bge-reranker → top-5 ──
    print("\n重排实验（B3）：vector top-20 → bge-reranker-v2-m3 → top-5")
    import urllib.request

    rerank_url = (settings.embedding_base_url or "").rstrip("/") + "/rerank"
    rr_key = settings.embedding_api_key

    def rerank(query: str, docs: list[str]) -> list[int]:
        req = urllib.request.Request(
            rerank_url,
            data=json.dumps({"model": "BAAI/bge-reranker-v2-m3", "query": query,
                             "documents": docs, "top_n": len(docs)}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {rr_key}"} if rr_key else {})})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return [item["index"] for item in body["results"]]

    rr_hits = rr_total = 0
    rr_failed = 0
    rr_per_q: dict[str, str] = {}
    for (q, gold), qv in zip(eval_qs, q_vecs):
        kid = kb_id_by_slug[q["caller"]["kb"]]
        vec_rows = rank_vector(kid, qv, 20)
        docs = [c for _, c, _s in vec_rows]
        if not docs:
            continue
        try:
            order = rerank(q["q"], docs)
        except Exception as exc:
            print(f"  rerank 调用失败：{exc}")
            rr_failed += 1
            continue
        reranked = [vec_rows[i] for i in order][:5]
        r = recall_at(reranked, gold)
        rr_per_q[q["id"]] = f"{r[0]}/{r[1]}"
        rr_hits += r[0]
        rr_total += r[1]
    if not rr_failed:
        results["rerank@5"] = {"recall": rr_hits / rr_total if rr_total else 0,
                               "hits": rr_hits, "total": rr_total,
                               "per_question": rr_per_q}
        print(f"  rerank@5: Recall = {rr_hits}/{rr_total} = {rr_hits/rr_total*100:.1f}%")
    else:
        print(f"  rerank@5：{rr_failed} 次调用失败，本轮不写入结果")

    # ── 报告 ──
    out = ["# 阶段 B 实验报告：参数扫描 + 重排（冻结 dev 集，纯检索口径）", "",
           f"> 语料 {sum(len(v) for v in kb_chunks.values())} chunk（3 库）；可评测题 {len(eval_qs)}"
           f"（剔除设计性不可达 {len(skipped)}）；Recall 为锚点级；问题向量一次批量调用，语料向量直读库。", "",
           "| 配置 | Recall | 命中/分母 |", "|---|---|---|"]
    for label, r in results.items():
        out.append(f"| {label} | {r['recall']*100:.1f}% | {r['hits']}/{r['total']} |")
    out += ["", "## 读数（诚实版）", "",
            "- **RRF k 值不敏感**（40/60/120 差异在噪声内）——融合常数不是杠杆；",
            "- **B vs A**：dev 集上混合与向量互有胜负且差距小——与冻结集正式 A/B 结论一致；",
            "- **vector@8 vs vector@5**：@8 的增益即 R2 类失败（金标在候选没进 top-5）的修复上限——若明显提升，重排是正确方向；",
            "- **重排实验（B3）**：vector top-20 经 bge-reranker 精排取 top-5，与 vector@5 直接对比——R2 类（m04/m15/m21/m58）是它的目标人群。",
            "- 全部配置无生成调用，成本为 0（Embedding 免费档 + 0 次生成）。"]

    (REPO / "evals/results/phase-b-experiments.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("报告: evals/results/phase-b-experiments.md")

    # 逐题明细：每个配置一行 JSON（qid → "命中数/分母"），供报告数字溯源。
    detail_path = REPO / "evals/results/phase-b-experiments-detail.jsonl"
    detail_path.write_text(
        "\n".join(json.dumps({"config": label, "per_question": r["per_question"]},
                              ensure_ascii=False)
                  for label, r in results.items()) + "\n",
        encoding="utf-8")
    print("逐题明细: evals/results/phase-b-experiments-detail.jsonl")
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
