#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_eval.py — S3-T03 通用评测运行器（真实模型，显式开关）。

用法：
    ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_eval.py \
        --dataset evals/smoke-10-draft.jsonl --mode vector --name ab-vector
    ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_eval.py \
        --dataset evals/smoke-10-draft.jsonl --mode hybrid --name ab-hybrid

参数化：数据集（任意 JSONL，字段同冒烟草稿格式）、检索模式（vector=实验 A /
hybrid=实验 B）、输出目录（evals/results/{name}/）。跳过语料入库用
--skip-ingest（语料已在库且未变时省 Embedding）。

诚实边界：不冻结留出集、不做提示词调参——那是 S3-T02 冻结流程的事；
本工具只保证"同一数据集 + 同一模式 = 可复跑报告"。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
sys.path.insert(0, str(REPO / "services" / "api"))
sys.path.insert(0, str(TOOLS))

if os.environ.get("ENABLE_REAL_MODEL_CALLS") != "1":
    print("拒绝运行：本工具会发起真实模型调用，必须显式 ENABLE_REAL_MODEL_CALLS=1")
    sys.exit(2)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from evidence_rag.db import engine  # noqa: E402
from evidence_rag.providers import get_clients  # noqa: E402
from evidence_rag.rag import answer_question  # noqa: E402
from evidence_rag.retrieval import search_chunks  # noqa: E402
from run_smoke_baseline import STATUS_MAP, ensure_kb, ensure_user, ingest_corpus  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evals/smoke-10-draft.jsonl")
    ap.add_argument("--mode", choices=["vector", "hybrid", "rerank"], default="vector")
    ap.add_argument("--name", required=True, help="输出子目录名（evals/results/{name}/）")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    session = sessionmaker(bind=engine)()
    generation, embedder = get_clients()
    settings_snapshot = {
        "date": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "dataset": args.dataset,
        "top_k": args.top_k,
        "generation": {"base": os.environ.get("GENERATION_BASE_URL", ""),
                       "model": "见 .env（本地端点）"},
        "embedding": {"model": "BAAI/bge-m3（免费标准版）", "dimension": 1024},
    }
    print(f"模式 {args.mode} | 数据集 {args.dataset}")

    if not args.skip_ingest:
        print("语料入库（真实 Embedding）…")
        t0 = time.perf_counter()
        corpus_index = ingest_corpus(session, embedder)
        print(f"入库完成 {len(corpus_index)} 份，耗时 {time.perf_counter() - t0:.1f}s")
    else:
        corpus_index = "skipped"
    user_id = ensure_user(session, "eval-runner")

    dataset_path = REPO / args.dataset
    questions = []
    for ln in dataset_path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        obj = json.loads(ln)
        if obj.get("_record_type") == "dataset-header":
            continue  # 冻结数据集的头行（状态与切分规则），不是题目
        questions.append(obj)
    out_dir = REPO / "evals" / "results" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    from evidence_rag.models import Chunk

    raws, summary = [], {}
    for q in questions:
        qid = q["id"]
        entry = {"id": qid, "type": q["type"], "question": q["q"]}
        if q["type"] == "权限":
            entry.update({"outcome": "占位跳过", "reason": "权限未实现，草稿注明仅占位"})
            raws.append(entry)
            summary.setdefault("占位", []).append(qid)
            continue
        kb_id = ensure_kb(session, q["caller"]["kb"])
        uid = ensure_user(session, "eval-runner")
        t0 = time.perf_counter()
        resp = answer_question(session, kb_id=kb_id, user_id=uid, question=q["q"],
                               generation=generation, embedder=embedder,
                               top_k=args.top_k, retrieval_mode=args.mode)
        elapsed = int((time.perf_counter() - t0) * 1000)
        answer_text = " ".join(seg.get("text", "") for seg in resp.get("segments", []))
        evidence = {e["id"]: e for e in resp.get("evidence", [])}

        def content_of(eid):
            row = session.get(Chunk, evidence[eid]["chunk_id"]) if eid in evidence else None
            return row.content if row else ""

        gold5 = [{"anchor": g["anchor"],
                  "in_top5": any(g["anchor"] in content_of(eid) for eid in evidence)}
                 for g in q.get("gold_evidence", [])]
        _, cands = search_chunks(session, kb_id=kb_id, query_text=q["q"], embedder=embedder,
                                 mode=args.mode, top_k=args.top_k, candidate_k=20)
        cand_text = "\n".join(c.content for c in cands)
        gold20 = [{"anchor": g["anchor"], "in_top20": g["anchor"] in cand_text}
                  for g in q.get("gold_evidence", [])]
        expected = STATUS_MAP.get(q["expected_status"], q["expected_status"])
        outcome = "pass" if resp["status"] == expected else f"status:{resp['status']}"
        entry.update({
            "outcome": outcome, "run_id": resp["run_id"], "elapsed_ms": elapsed,
            "answer": answer_text[:400], "error_class": resp.get("error_class"),
            "error_detail": resp.get("error_detail"),
            "citations": sorted({cid for seg in resp.get("segments", [])
                                 for cid in seg.get("citation_ids", [])}),
            "gold_top5": gold5, "gold_top20": gold20,
            "must_not": [{"phrase": m, "leaked": m in answer_text}
                         for m in q.get("must_not_include", [])],
        })
        raws.append(entry)
        if outcome == "pass":
            key = "pass"
        elif not any(h["in_top20"] for h in gold20):
            key = "R1"
        elif not any(h["in_top5"] for h in gold5):
            key = "R2"
        else:
            key = "G*"
        summary.setdefault(key, []).append(qid)
        print(f"  {qid} [{q['type']}] -> {resp['status']} ({elapsed}ms) 归因暂记={key}")

    (out_dir / "raw.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in raws) + "\n", encoding="utf-8")
    settings_snapshot["corpus"] = corpus_index
    (out_dir / "config-snapshot.json").write_text(
        json.dumps(settings_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# 评测报告：{args.name}（模式 {args.mode}，数据集 {args.dataset}）",
        "",
        f"> 生成时间：{settings_snapshot['date']}。小样本/草稿题不外推结论，详见 raw.jsonl。",
        "",
        "| 结果 | 题目 |", "|---|---|",
    ]
    for key, ids in sorted(summary.items()):
        lines.append(f"| {key} | {', '.join(ids)} |")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告: {out_dir / 'report.md'}")
    session.commit()
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
