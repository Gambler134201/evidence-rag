"""聚合正式 A/B 的 6 轮结果：通过率、稳定性、Recall@5、时延，分冻结/留出集报告。"""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[2]

def load(name):
    p = REPO / "evals/results" / name / "raw.jsonl"
    return {r["id"]: r for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())}

# 冻结集 split 信息
frozen = {}
for ln in (REPO / "evals/datasets/main-80.jsonl").read_text(encoding="utf-8").splitlines()[1:]:
    if ln.strip():
        r = json.loads(ln)
        frozen[r["id"]] = r["split"]

modes = ["vector", "hybrid"]
runs = {m: [load(f"formal-ab/{m}-r{i}") for i in (1, 2, 3)] for m in modes}

lines = ["# 正式 A/B 对照报告：vector vs hybrid（冻结主集 80 条，每题 n=3，真实模型）", ""]
lines.append("> 运行日期：见各 config-snapshot.json。数据集 `evals/datasets/main-80.jsonl`（已冻结）。")
lines.append("> A=精确向量；B=向量+BM25(jieba)+RRF(k=60)。六轮运行原始记录见 formal-ab/ 各子目录。")
lines.append("> 稳定性口径：同一题 3 次运行状态全部一致记「稳定」；headline 通过率以**留出集（freeze 40 条）**为准，开发集（dev 40）仅用于观察。")
lines.append("")

for mode in modes:
    lines.append(f"## 模式 {mode}（3 轮）")
    lines.append("")
    for i, run in enumerate(runs[mode], 1):
        ex = [r["elapsed_ms"] for r in run.values() if r.get("elapsed_ms")]
        ex.sort()
        p50 = statistics.median(ex) / 1000
        p95 = ex[int(len(ex) * 0.95) - 1] / 1000
        passed = sum(1 for r in run.values() if r["outcome"] == "pass")
        lines.append(f"- 第 {i} 轮：通过 {passed}/80，P50 {p50:.1f}s，P95 {p95:.1f}s")
    lines.append("")

lines.append("## 稳定题与不稳定题（按 3 轮状态一致性）")
lines.append("")
unstable = {m: [] for m in modes}
for mode in modes:
    for qid in sorted(runs[mode][0].keys()):
        if any(qid not in run for run in runs[mode]):
            continue
        states = {run[qid].get("outcome", "?") for run in runs[mode]}
        if len(states) > 1:
            unstable[mode].append(qid)
lines.append(f"- vector 不稳定题：{', '.join(unstable['vector']) or '无'}")
lines.append(f"- hybrid 不稳定题：{', '.join(unstable['hybrid']) or '无'}")
lines.append("")

lines.append("## 分集合通过率（3 轮中至少 2 轮通过记「稳定通过」）")
lines.append("")
lines.append("| 集合 | vector 稳定通过 | hybrid 稳定通过 |")
lines.append("|---|---|---|")
for split_name in ["dev", "freeze"]:
    row = [split_name]
    for mode in modes:
        stable = 0
        total = 0
        for qid, split in frozen.items():
            if split != split_name or any(qid not in run for run in runs[mode]):
                continue
            total += 1
            passes = sum(1 for run in runs[mode] if run[qid].get("outcome") == "pass")
            if passes >= 2:
                stable += 1
        row.append(f"{stable}/{total}")
    lines.append("| " + " | ".join(row) + " |")
lines.append("")

lines.append("## 逐题明细")
lines.append("")
lines.append("| 题 | 类别 | 集合 | v-r1 | v-r2 | v-r3 | h-r1 | h-r2 | h-r3 |")
lines.append("|---|---|---|---|---|---|---|---|---|")
abbr = {"pass": "✓", }
def abbr_state(r):
    if r.get("outcome") == "占位跳过":
        return "占位"
    if r["outcome"] == "pass":
        return "✓"
    return r["outcome"].split(":")[-1] or "?"
for qid in sorted(runs["vector"][0].keys()):
    cells = []
    for mode in modes:
        for run in runs[mode]:
            r = run.get(qid)
            cells.append(abbr_state(r) if r else "—")
    split = frozen.get(qid, "?")
    lines.append(f"| {qid} | {runs['vector'][0][qid]['type']} | {split} | " + " | ".join(cells) + " |")

out = REPO / "evals/results/formal-ab/report.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written:", out)
