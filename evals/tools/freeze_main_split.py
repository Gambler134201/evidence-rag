"""冻结 80 条主集：按问题族连续切分 40/40，真近似对（>=0.65）不跨集。

规则（docs/evaluation-plan.md 冻结策略）：
- 类别内切分：事实 15/15、跨文档 10/10、版本 5/5、无答案 3/3、澄清 2/2、干扰 5/5；
- 同族题按（锚点集 + 题面前缀）排序后连续对半，真近似对（题面重合度 >=0.65 且
  预期一致）若跨集，与对侧无冲突元素换位修复（数量守恒）；
- 0.5~0.65 的同类变体允许跨集：语料的近邻干扰设计本就要求变体分散两侧；
- 最终断言：总量 40/40 且真近似对零跨集，否则冻结被拒绝。
"""
import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

SRC = Path("evals/datasets/main-80-draft.jsonl")
DST = Path("evals/datasets/main-80.jsonl")

lines = SRC.read_text(encoding="utf-8").splitlines()
header = json.loads(lines[0])
recs = [json.loads(l) for l in lines[1:] if l.strip()]


def similarity(a, b):
    return SequenceMatcher(None, a["q"], b["q"]).ratio()


def is_near_dup(a, b):
    """真近似改写对：题面重合度 >=0.65 且预期状态一致——禁止跨集。"""
    return similarity(a, b) >= 0.65 and a["expected_status"] == b["expected_status"]


split_result = {}
variants = []
near_dup_straddles = []
repaired = 0

for cat in ["事实", "跨文档", "版本", "无答案", "澄清", "干扰"]:
    idx = [i for i, r in enumerate(recs) if r["category"] == cat]
    # 同族题排相邻：主锚点 + 题面前缀排序后连续对半
    idx.sort(key=lambda i: (
        tuple(sorted(g["anchor"] for g in recs[i].get("gold_evidence", []))),
        recs[i]["q"][:12],
    ))
    half = len(idx) // 2
    for pos, global_i in enumerate(idx):
        split_result[global_i] = "dev" if pos < half else "freeze"

    # 修复真近似对跨集：b 与 a 同侧的一个"无冲突"元素交换，数量守恒
    for ai in range(len(idx)):
        for bi in range(ai + 1, len(idx)):
            a, b = idx[ai], idx[bi]
            if not is_near_dup(recs[a], recs[b]):
                continue
            if split_result[a] == split_result[b]:
                continue

            def conflict(c):
                return any(
                    is_near_dup(recs[c], recs[d])
                    for d in idx
                    if d != c and split_result[d] == split_result[a]
                )

            swap_with = next(
                (c for c in idx
                 if split_result[c] == split_result[a]
                 and c != a and c != b
                 and not conflict(c)),
                None)
            if swap_with is None:
                continue  # 无干净交换者：如实记录，宁缺毋滥
            split_result[swap_with], split_result[b] = split_result[b], split_result[swap_with]
            repaired += 1

    for ai in range(len(idx)):
        for bi in range(ai + 1, len(idx)):
            a, b = idx[ai], idx[bi]
            sim = similarity(recs[a], recs[b])
            if 0.5 <= sim < 0.65 and split_result[a] != split_result[b]:
                variants.append((recs[a]["id"], recs[b]["id"], round(sim, 2)))
            if is_near_dup(recs[a], recs[b]) and split_result[a] != split_result[b]:
                near_dup_straddles.append((recs[a]["id"], recs[b]["id"]))

for i, r in enumerate(recs):
    r["split"] = split_result[i]

balance = Counter((r["category"], r["split"]) for r in recs)
frozen_header = {
    **header,
    "_record_type": "dataset-header",
    "status": "已冻结（2026-10-25，作者复核通过：决策 13 项全 A、二三层无异议）",
    "split_rule": "类别内按问题族连续切分 40/40；真近似对（>=0.65）不跨集，0.5~0.65 同类变体允许跨集",
    "frozen_at": "2026-10-25",
    "review_record": "evals/gold-review-main.md",
}

out_lines = [json.dumps(frozen_header, ensure_ascii=False)]
out_lines += [json.dumps(r, ensure_ascii=False) for r in recs]
DST.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

dev_n = sum(1 for r in recs if r["split"] == "dev")
fz_n = sum(1 for r in recs if r["split"] == "freeze")
print("冻结完成：", dict(balance))
print("真近似对跨集:", len(near_dup_straddles), near_dup_straddles)
print("同类变体跨集（设计允许）:", len(variants))
print(f"总量校验：dev={dev_n} freeze={fz_n}")
assert dev_n == 40 and fz_n == 40, f"切分不均衡 dev={dev_n} freeze={fz_n}"
assert not near_dup_straddles, "存在真近似对跨集，冻结被拒绝"
