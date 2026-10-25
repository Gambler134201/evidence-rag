#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate_min_score.py — A1 拒答阈值校准复算工具（只读库，不发任何模型调用）。

复现 evals/results/min-score-calibration.md 的两张表：
1. top1 证据分数分布：formal-ab vector 3 轮 × dev 40 题的 C1 证据分数，按
   expected_status（answer/clarify/refuse）分桶，给 n/min/P25/median/P75/max；
2. 阈值扫描：0.30~0.50 步长 0.05 各档下 answer 题会被误拒（top1 < 阈值）的次数。

数据源：
- 运行记录：evals/results/formal-ab/vector-r1|2|3/raw.jsonl 的 run_id 字段；
- 题目元数据：evals/datasets/main-80.jsonl（跳过 _record_type 头行，只取 split=dev）；
- top1 分数：dev 数据库 query_run_evidence 表中 evidence_no='C1' 行的 score。

运行（不需要 ENABLE_REAL_MODEL_CALLS，本工具不调模型）：
    .venv/Scripts/python.exe evals/tools/calibrate_min_score.py

诚实边界：与当时一次性分析脚本一致采用线性插值百分位（等价 numpy.percentile
默认法 / statistics.quantiles inclusive）；分数来自运行时落库的检索器原始分。
"""
import json
import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from evidence_rag.db import engine  # noqa: E402

ROUNDS = ["vector-r1", "vector-r2", "vector-r3"]
THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50]
BUCKET_ORDER = ["answer", "clarify", "refuse"]


def percentile(sorted_vals: list[float], p: float) -> float | None:
    """线性插值百分位（numpy.percentile 默认法）。输入必须已升序。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main() -> int:
    # ── 题目元数据：dev 集的 expected_status ──
    status_by_qid: dict[str, str] = {}
    for ln in (REPO / "evals/datasets/main-80.jsonl").read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("_record_type") == "dataset-header":
            continue
        if r.get("split") == "dev":
            status_by_qid[r["id"]] = r["expected_status"]
    print(f"dev 题：{len(status_by_qid)}"
          f"（{ {s: sum(1 for v in status_by_qid.values() if v == s) for s in BUCKET_ORDER} }）")

    # ── 运行记录：vector 3 轮 × dev 题 → run_id ──
    runs: list[tuple[str, str]] = []  # (qid, run_id)
    missing_run_id = []
    for rnd in ROUNDS:
        path = REPO / "evals/results/formal-ab" / rnd / "raw.jsonl"
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            rec = json.loads(ln)
            qid = rec["id"]
            if qid not in status_by_qid:
                continue  # 只统计 dev 题
            rid = rec.get("run_id")
            if not rid:
                missing_run_id.append(f"{rnd}/{qid}")
                continue
            runs.append((qid, rid))
    print(f"dev 运行记录：{len(runs)} 条（{len(ROUNDS)} 轮）"
          + (f"；无 run_id：{missing_run_id}" if missing_run_id else ""))

    # ── 查库：C1 证据分数 ──
    session = sessionmaker(bind=engine)()
    query = text("""
        SELECT run_id::text AS rid, score
        FROM query_run_evidence
        WHERE evidence_no = 'C1' AND run_id::text IN :run_ids
    """).bindparams(bindparam("run_ids", expanding=True))
    rows = session.execute(query, {"run_ids": [rid for _, rid in runs]}).all()
    session.close()
    score_by_run = {rid: score for rid, score in rows}
    missing_c1 = [f"{qid}" for qid, rid in runs if rid not in score_by_run
                  or score_by_run[rid] is None]
    print(f"查到 C1 分数：{sum(1 for _, r in runs if r in score_by_run)}/{len(runs)}"
          + (f"；缺 C1 或分数为空的运行（按题）：{sorted(set(missing_c1))}" if missing_c1 else ""))

    # ── 按 expected_status 分桶 ──
    buckets: dict[str, list[float]] = {s: [] for s in BUCKET_ORDER}
    for qid, rid in runs:
        score = score_by_run.get(rid)
        if score is None:
            continue
        buckets[status_by_qid[qid]].append(score)

    print("\n## 分数分布（top1 证据分数 = C1）\n")
    header = f"| 预期状态 | n | min | P25 | median | P75 | max |"
    print(header)
    print("|---|---|---|---|---|---|---|")
    for name in BUCKET_ORDER:
        vals = sorted(buckets[name])
        if not vals:
            print(f"| {name} | 0 | - | - | - | - | - |")
            continue
        cells = [f"{percentile(vals, p):.3f}" for p in (0.0, 0.25, 0.5, 0.75, 1.0)]
        print(f"| {name} | {len(vals)} | " + " | ".join(cells) + " |")
    ans_sorted = sorted(buckets["answer"])
    if ans_sorted:
        print(f"\n（补充）answer 桶 P10 = {percentile(ans_sorted, 0.10):.3f}，"
              f"P05 = {percentile(ans_sorted, 0.05):.3f}")

    # ── 阈值扫描：answer 题误拒数（top1 < 阈值即被拒答）──
    print("\n## 阈值扫描（answer 题误拒数）\n")
    print("| 阈值 | answer 运行数 | 误拒数 |")
    print("|---|---|---|")
    for t in THRESHOLDS:
        false_refusals = sum(1 for s in buckets["answer"] if s < t)
        print(f"| {t:.2f} | {len(buckets['answer'])} | {false_refusals} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
