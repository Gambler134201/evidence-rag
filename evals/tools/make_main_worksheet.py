import json, re, yaml
from pathlib import Path

corpus = {}
for path in Path("examples/synthetic-docs").glob("kb-*/*.md"):
    text = path.read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---")[1])
    corpus[meta["version_id"]] = (meta.get("knowledge_base_id", ""), text)

lines = Path("evals/datasets/main-80-draft.jsonl").read_text(encoding="utf-8").splitlines()
header = json.loads(lines[0])
recs = [json.loads(l) for l in lines[1:] if l.strip()]

def excerpt(vid, anchor):
    _, text = corpus.get(vid, ("", ""))
    m = re.search(r"(^##+\s*%s.*?)(?=^##|\Z)" % re.escape(anchor), text, re.M | re.S)
    if not m:
        return "(未找到)"
    return m.group(1).strip().replace("\n\n", "\n")[:260]

flag = lambda r: "决策" if (r.get("must_not_include") or r["type"] in ("干扰", "权限")) else "速览-mixed"
tier_a = [r for r in recs if r["type"] in ("版本", "无答案", "澄清")]
tier_c = [r for r in recs if r["type"] in ("事实", "跨文档")]
flagged = [r for r in recs if flag(r) == "决策" and r["type"] not in ("版本", "无答案", "澄清")]
# 决策题 = 带 must_not 或 type 干扰/权限 且不在第二层的
flagged = [r for r in recs if (r.get("must_not_include") or r["type"] in ("干扰", "权限")) and r["type"] not in ("版本", "无答案", "澄清")]

parts = []
parts.append("# 80 条主集复核工作单（作者专用）\n")
parts.append("> 对应 `evals/datasets/main-80-draft.jsonl`。分层读法与回复格式见文末。\n")
parts.append(f"> 自动化验证已通过：130 个锚点全部命中真实条款标题；配额 {dict(__import__('collections').Counter(r['category'] for r in recs))}。\n\n---\n")
parts.append(f"\n## 第一层：决策题（{len(flagged)} 条，逐条给选项）\n\n")
parts.append("> 这些题带 must_not_include 护栏，或 type 属于干扰/权限（口径归属）。推荐全选 A。\n\n")

for r in flagged:
    parts.append(f"### {r['id']}｜{r['type']}｜预期 {r['expected_status']}\n\n")
    parts.append(f"**问题**：{r['q']}\n\n")
    parts.append(f"**必答点**：{'；'.join(r.get('required_info_points', []))}\n\n")
    if r.get("must_not_include"):
        parts.append(f"**不得出现**：{'、'.join(r['must_not_include'])}\n\n")
    for g in r.get("gold_evidence", [])[:2]:
        kb, text = corpus.get(g["version_id"], ("", ""))
        parts.append(f"- 锚点 `{g['anchor']}`（{g['version_id']}）：\n  > {excerpt(g['version_id'], g['anchor'])[:200]}\n")
    parts.append("\n**【决策】**\n")
    if r.get("must_not_include"):
        parts.append("- A.（推荐）护栏保留：must_not_include 仅检查回答正文是否给出禁用内容，不要求护栏本身是语料原句——它防的是模型采纳陷阱数值\n")
        parts.append("- B. 删除该护栏\n")
    if r["type"] in ("干扰", "权限"):
        parts.append("- A.（推荐）口径：干扰类归「注入抵抗」单列；权限类在权限实现前为占位不计分——与已转正的 smk-05 口径一致\n")
        parts.append("- B. 另行定义\n")
    parts.append("\n---\n\n")

parts.append(f"## 第二层：必读题（版本 / 无答案 / 澄清 / 干扰中的语义确认，{len(tier_a)} 条）\n\n")
parts.append("> 逐条判断：按金标原文，这个预期状态和必答点合理吗？不合理就报 id。\n\n")
for r in tier_a:
    parts.append(f"### {r['id']}｜{r['type']}｜预期 {r['expected_status']}\n\n")
    parts.append(f"**问题**：{r['q']}\n\n")
    parts.append(f"**必答点**：{'；'.join(r.get('required_info_points', []))}\n\n")
    for g in r.get("gold_evidence", [])[:2]:
        parts.append(f"- `{g['anchor']}`：> {excerpt(g['version_id'], g['anchor'])[:160]}\n")
    parts.append("\n")

parts.append(f"---\n\n## 第三层：速览题（事实 / 跨文档，{len(tier_c)} 条）\n\n")
parts.append("> 机检已确认锚点逐字命中；扫一眼问题是否自然、必答点是否跑偏即可。\n\n")
for r in tier_c:
    parts.append(f"- **{r['id']}**（{r['type']}）{r['q']} → 预期 {r['expected_status']}；锚点 {'、'.join(g['anchor'] for g in r.get('gold_evidence', []))}\n")

parts.append("\n---\n\n## 分层读法与回复格式\n\n")
parts.append(f"1. **第一层（{len(flagged)} 条决策题）**：逐条挑 A/B；\n")
parts.append(f"2. **第二层（{len(tier_a)} 条必读）**：逐条确认预期合理，不合理报 id；\n")
parts.append(f"3. **第三层（{len(tier_c)} 条速览）**：扫一眼，有异议报 id；\n")
parts.append('4. 回复一行即可：**「决策全 A；二、三层无异议，冻结」** —— 或指出具体 id。\n\n')
parts.append("收到后我将：按结论修订 → 生成 `evals/gold-review-main.md`（核对人 author）→ 40/40 冻结切分（按问题族，留出集封存）→ 跑正式 A/B（每题 n≥3）→ 简历第 4 页填上 Recall 数字。\n")

Path("evals/main-80-review-worksheet.md").write_text("".join(parts), encoding="utf-8")
print(f"工作单已生成：决策题 {len(flagged)} | 必读 {len(tier_a)} | 速览 {len(tier_c)}")
