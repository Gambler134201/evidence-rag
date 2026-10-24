#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_smoke_baseline.py — S1-T10 冒烟基线（真实模型，显式开关）。

必须以 ENABLE_REAL_MODEL_CALLS=1 运行：
    ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_smoke_baseline.py

行为：在开发库新建/复用基线知识库，真实入库当前语料（真实 Embedding），
逐条运行 evals/smoke-10-draft.jsonl（真实生成），输出机械核对报告与原始
记录到 evals/results/stage1-baseline/。调用规模：语料 Embedding 若干批 +
每题 1 次 Embedding + 1 次生成（本地模型无 API 费用，Embedding 免费档）。

诚实边界：题目草稿的 6 个复核点尚未经作者人工确认；报告标注“基线观察，
非准确率结论”（小样本）；smk-05（越权）在权限实现前只能记占位。
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

if os.environ.get("ENABLE_REAL_MODEL_CALLS") != "1":
    print("拒绝运行：本脚本会发起真实模型调用，必须显式 ENABLE_REAL_MODEL_CALLS=1")
    sys.exit(2)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from evidence_rag.config import get_settings  # noqa: E402
from evidence_rag.ingest import ingest_version, publish_build  # noqa: E402
from evidence_rag.models import Document, KnowledgeBase  # noqa: E402
from evidence_rag.providers import get_clients  # noqa: E402
from evidence_rag.rag import answer_question  # noqa: E402
from evidence_rag.retrieval import search_similar_chunks  # noqa: E402

CORPUS = [
    ("kb-a", "A 交付规则 v1", "delivery-rules-v1.md"),
    ("kb-a", "A 交付规则 v2", "delivery-rules-v2.md"),
    ("kb-a", "A 验收 FAQ", "acceptance-faq.md"),
    ("kb-a", "A 整改手册", "rectification-manual.md"),
    ("kb-b", "B 同名交付规则", None),  # kb-b 由题面需要时另行入库
]
STATUS_MAP = {"answer": "answered", "clarify": "needs_clarification", "refuse": "insufficient_evidence"}


def ensure_kb(session, slug: str) -> int:
    kb = session.execute(select(KnowledgeBase).where(KnowledgeBase.slug == slug)).scalar_one_or_none()
    if kb is None:
        kb = KnowledgeBase(name=slug, slug=slug)
        session.add(kb)
        session.flush()
    return kb.id


def ensure_user(session, username: str) -> int:
    from evidence_rag.models import User

    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(username=username, password_hash="baseline-local", display_name="基线运行")
        session.add(user)
        session.flush()
    return user.id


def ingest_corpus(session, embedder) -> dict[str, dict]:
    """按语料元数据分库入库；同一逻辑文档（document_id）归入同一 Document，
    只发布其最新可用版本（排除 draft/deprecated 后取 effective_at 最大者），
    避免新旧版本同时可检索。"""
    import yaml

    results: dict[str, dict] = {}
    docs_dir = REPO / "examples" / "synthetic-docs"
    groups: dict[tuple, list] = {}
    for path in sorted(docs_dir.glob("kb-*/*.md")):
        text = path.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---")[1])
        groups.setdefault((meta["knowledge_base_id"], meta["document_id"]), []).append((meta, path))

    for (kb_slug, _doc_id), members in sorted(groups.items()):
        kb_id = ensure_kb(session, kb_slug)
        title = members[0][0].get("doc_title") or members[0][0]["title"]
        doc = Document(kb_id=kb_id, title=title)
        session.add(doc)
        session.flush()
        publish_target = None
        for meta, path in members:
            r = ingest_version(
                session, kb_id=kb_id, document_id=doc.id,
                filename=path.name, data=path.read_bytes(),
                embedder=embedder,
            )
            if r.get("failed"):
                print(f"  !! 语料入库失败 {path.name}: {r['error_class']}")
                continue
            results[meta["version_id"]] = {"build_id": r["build_id"], "n_chunks": r["n_chunks"]}
            if meta.get("status") not in ("draft", "deprecated", "historical"):
                eff = meta.get("effective_at", "")
                if publish_target is None or eff > publish_target[0]:
                    publish_target = (eff, r)
        if publish_target:
            _, r = publish_target
            publish_build(session, document_id=doc.id, version_id=r["version_id"], build_id=r["build_id"])
            print(f"  {kb_slug}/{_doc_id}: 发布 {r['version_id']}（{len(members)} 个版本）")
        else:
            print(f"  {kb_slug}/{_doc_id}: 无可发布版本！")
    session.flush()
    return results


def main() -> int:
    settings = get_settings()
    from evidence_rag.db import engine

    session = sessionmaker(bind=engine)()
    generation, embedder = get_clients()
    print(f"生成: {settings.generation_model or 'mock'} @ {settings.generation_base_url or '-'}")
    print(f"Embedding: {settings.embedding_model or 'mock'} @ {settings.embedding_base_url or '-'}")

    print("语料入库（真实 Embedding）…")
    t0 = time.perf_counter()
    corpus_index = ingest_corpus(session, embedder)
    print(f"入库完成 {len(corpus_index)} 份，耗时 {time.perf_counter() - t0:.1f}s")

    questions = [
        json.loads(ln)
        for ln in (REPO / "evals" / "smoke-10-draft.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    out_dir = REPO / "evals" / "results" / "stage1-baseline"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw.jsonl"
    report_path = out_dir / "report.md"

    raws = []
    summary: dict[str, list] = {}
    for q in questions:
        qid = q["id"]
        entry: dict = {"id": qid, "type": q["type"], "question": q["q"]}
        if q["type"] == "权限":
            entry.update({"outcome": "占位跳过", "reason": "权限未实现（S2-T02），草稿注明只能作断言占位"})
            raws.append(entry)
            summary.setdefault("占位", []).append(qid)
            continue
        kb_id = ensure_kb(session, q["caller"]["kb"])
        user_id = ensure_user(session, "baseline")
        started = time.perf_counter()
        resp = answer_question(
            session, kb_id=kb_id, user_id=user_id, question=q["q"],
            generation=generation, embedder=embedder,
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        answer_text = " ".join(seg.get("text", "") for seg in resp.get("segments", []))
        cited = {cid for seg in resp.get("segments", []) for cid in seg.get("citation_ids", [])}
        evidence = {e["id"]: e for e in resp.get("evidence", [])}

        # 金标锚点核对：最终证据回查 chunk 正文；top-20 候选用于 R1/R2 归因
        from evidence_rag.models import Chunk

        def content_of(eid: str) -> str:
            row = session.get(Chunk, evidence[eid]["chunk_id"])
            return row.content if row else ""

        gold_hits_top5 = [
            {"anchor": g["anchor"], "in_top5": any(g["anchor"] in content_of(eid) for eid in evidence)}
            for g in q.get("gold_evidence", [])
        ]
        cand_top20, _ = search_similar_chunks(
            session, kb_id=kb_id, query_text=q["q"], embedder=embedder, top_k=5, candidate_k=20,
        )
        cand20_text = "\n".join(c.content for c in cand_top20)
        gold_hits_c20 = [
            {"anchor": g["anchor"], "in_top20": g["anchor"] in cand20_text}
            for g in q.get("gold_evidence", [])
        ]
        info_checks = [
            {"point": p, "present": p in answer_text or p in cand20_text}
            for p in q.get("required_info_points", [])
        ]
        must_not_hits = [
            {"phrase": m, "leaked": m in answer_text} for m in q.get("must_not_include", [])
        ]
        expected = STATUS_MAP.get(q["expected_status"], q["expected_status"])
        outcome = "pass" if resp["status"] == expected else f"status:{resp['status']}!=expected:{expected}"
        entry.update({
            "outcome": outcome,
            "run_id": resp["run_id"],
            "elapsed_ms": elapsed,
            "answer": answer_text[:400],
            "error_class": resp.get("error_class"),
            "error_detail": resp.get("error_detail"),
            "citations": sorted(cited),
            "gold_top5": gold_hits_top5,
            "gold_top20": gold_hits_c20,
            "info_points": info_checks,
            "must_not": must_not_hits,
        })
        raws.append(entry)
        key = "pass" if outcome == "pass" else ("R1" if not any(h["in_top20"] for h in gold_hits_c20)
                                               else ("R2" if not any(h["in_top5"] for h in gold_hits_top5)
                                                     else "G*"))
        summary.setdefault(key, []).append(qid)
        print(f"  {qid} [{q['type']}] -> {resp['status']} ({elapsed}ms) 归因暂记={key}")

    with raw_path.open("w", encoding="utf-8") as fh:
        for r in raws:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    settings_cfg = {
        "date": datetime.now(timezone.utc).isoformat(),
        "generation": {"base": settings.generation_base_url, "model": settings.generation_model},
        "embedding": {"base": settings.embedding_base_url, "model": settings.embedding_model,
                      "dimension": settings.embedding_dimension},
        "pipeline": "v1 exact-vector top_k=5 candidate_k=20",
        "corpus": corpus_index,
        "questions": "evals/smoke-10-draft.jsonl（草稿，锚点作者复核未完成）",
    }
    (out_dir / "config-snapshot.json").write_text(
        json.dumps(settings_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 阶段 1 冒烟基线报告（草稿）",
        "",
        f"> 生成时间：{settings_cfg['date']}。**基线观察，非准确率结论**（10 条小样本）。",
        "> 题目为草稿（`smoke-10-draft.jsonl`），6 个复核点未经作者人工确认，结论不对外。",
        "> 检索=精确向量（真实 bge-m3）；生成=本地端点（真实）；调用记录见 raw.jsonl。",
        "",
        "| 结果 | 题目 |",
        "|---|---|",
    ]
    for key, ids in sorted(summary.items()):
        lines.append(f"| {key} | {', '.join(ids)} |")
    lines += ["", "逐题明细见 raw.jsonl；机械核对口径：预期状态、必含信息点、must_not 泄漏、",
              "金标锚点 top-5/top-20 命中（R1=候选 20 都没有，R2=在 20 不在 5，其余 G* 待人工归因）。"]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {report_path}")
    session.commit()  # 运行记录入库（query_runs）
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
