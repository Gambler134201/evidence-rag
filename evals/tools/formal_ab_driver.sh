#!/usr/bin/env bash
# 正式 A/B：冻结主集 80 条，vector/hybrid 各 3 轮（真实模型）。
# 用法：ENABLE_REAL_MODEL_CALLS=1 bash evals/tools/formal_ab_driver.sh
set -e
cd "$(dirname "$0")/../.."
for mode in vector hybrid; do
  for i in 1 2 3; do
    echo "=== formal A/B: $mode round $i ==="
    ENABLE_REAL_MODEL_CALLS=1 .venv/Scripts/python.exe evals/tools/run_eval.py \
      --dataset evals/datasets/main-80.jsonl --mode "$mode" \
      --name "formal-ab/$mode-r$i" --skip-ingest
  done
done
echo "=== 聚合 ==="
.venv/Scripts/python.exe evals/tools/compare_formal_ab.py
