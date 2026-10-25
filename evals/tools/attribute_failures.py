"""B1：正式 A/B 系统性失败题的六类归因（数据来自 formal-ab 原始记录）。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[2]

def load(name):
    return {r["id"]: r for r in map(json.loads, (REPO / "evals/results" / name / "raw.jsonl").read_text(encoding="utf-8").splitlines())}

frozen = {}
for ln in (REPO / "evals/datasets/main-80.jsonl").read_text(encoding="utf-8").splitlines()[1:]:
    if ln.strip():
        r = json.loads(ln)
        frozen[r["id"]] = {"split": r["split"], "cat": r["category"], "exp": r["expected_status"]}

runs = {m: [load(f"formal-ab/{m}-r{i}") for i in (1, 2, 3)] for m in ("vector", "hybrid")}

# 找系统性失败：某题在某模式下 ≥2 轮非 pass
report = []
for mode in ("vector", "hybrid"):
    per_q = defaultdict(list)
    for run in runs[mode]:
        for qid, r in run.items():
            per_q[qid].append(r)
    for qid, rs in sorted(per_q.items()):
        fails = [r for r in rs if r.get("outcome") != "pass" and r.get("outcome") != "占位跳过"]
        if len(fails) < 2:
            continue
        m = frozen[qid]
        g5 = [h["in_top5"] for r in rs for h in r.get("gold_top5", [])]
        g20 = [h["in_top20"] for r in rs for h in r.get("gold_top20", [])]
        any_gold20 = any(g20)
        # 机械归因：金标不在候选 → R1；在候选不在 top5 → R2；在 top5 仍失败 → G 类
        if not any_gold20:
            attr = "R1（金标不在 top-20 候选）"
        elif not any(g5):
            attr = "R2（金标在候选但未进 top-5）"
        else:
            attr = "G*（证据已进 top-5，生成/口径侧失败）"
        exp = m["exp"]
        outcomes = [r.get("outcome", "?").split(":")[0] for r in rs]
        lines_out = []
        for r in fails[:1]:
            lines_out.append((r.get("answer") or "")[:120])
            if r.get("error_class"):
                lines_out.append(f"error: {r['error_class']}")
        report.append({
            "mode": mode, "qid": qid, "cat": m["cat"], "split": m["split"], "exp": exp,
            "outcomes": outcomes, "attr": attr, "sample": " | ".join(lines_out),
            "gold5": "/".join("✓" if x else "✗" for x in g5),
            "gold20": "/".join("✓" if x else "✗" for x in g20),
        })

out = ["# 失败题归因报告（B1）", "",
       "> 数据：正式 A/B 六轮（vector/hybrid × 3）。系统性失败 = 同题同模式 ≥2/3 轮非 pass。",
       "> 机械归因规则：金标不在 top-20 → R1；在 top-20 不在 top-5 → R2；在 top-5 → G 类（生成/口径侧，需人工细分）。", "",
       "| 模式 | 题 | 类别 | 集合 | 预期 | 3 轮状态 | 归因 | 答案摘录 |", "|---|---|---|---|---|---|---|---|"]
for x in report:
    rows = "→".join(x["outcomes"])
    out.append(f"| {x['mode']} | {x['qid']} | {x['cat']} | {x['split']} | {x['exp']} | {rows} | {x['attr']} | {x['sample'][:80]} |")

out.append("")
out.append("## 汇总")
by = defaultdict(list)
for x in report:
    by[x["attr"]].append(f"{x['mode']}/{x['qid']}")
for k in sorted(by):
    out.append(f"- {k}: {', '.join(by[k])}")
out.append("")
out.append("## 修复方向")
out.append("")
out.append("- R1/G 类（m36 等）：检索不足——进入 B2 参数扫描与 B4 查询扩展的验证对象；")
out.append("- G2（m67/m68 应澄清未澄清，两模式一致）：契约 v2.1 仍未覆盖的澄清形态，进入提示词 v3 迭代；")
out.append("- hybrid 特有失败（m57/m58/m19/m21）：BM25+RRF 引入的候选扰动——若阶段 B2 调参无法挽回，维持向量为默认模式的决策。")
out.append("")
out.append("注：归因为机械规则 + 人工复核摘要；G 类细分（G1/G2/G3）需人工确认语义。")

(REPO / "evals/results/failure-attribution.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"系统性失败 {len(report)} 条，报告已写入 evals/results/failure-attribution.md")
for x in report:
    print(f"  {x['mode']}/{x['qid']} [{x['cat']}] {x['attr']}")
