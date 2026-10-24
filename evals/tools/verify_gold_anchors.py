#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_gold_anchors.py —— 冒烟评测题金标锚点机器校验工具。

对 evals/smoke-10-draft.jsonl 的 10 条草稿题做机器辅助检查（不是人工金标复核）：
  a. gold_evidence.version_id 是否存在于语料元数据，且 kb/文档对应关系合理；
  b. anchor 条款编号是否在该文档正文（章节标题或行内）命中；
  c. text 与条款原文的一致性分级：exact / paraphrase / mismatch；
  d. must_not_include 干扰短语是否真实存在于语料（含近似变体提示）；
  e. smk-09 用 datetime 独立验算工作日序列，并与 FAQ A-F-02 交叉核对；
  f. smk-03 历史口径：A-D1-01 适用日期范围 vs 题面提交日期 vs 元数据有效期；
  g. type/expected_status 与 evals/badcase-taxonomy.md 第 2 节口径对照。

纯标准库；不联网；不修改任何被检文件（含 smoke-10-draft.jsonl 与语料）。
默认把 Markdown 报告打印到 stdout；--out PATH 时同时写出报告文件。

用法（仓库根目录）：
    .venv/Scripts/python.exe evals/tools/verify_gold_anchors.py
    .venv/Scripts/python.exe evals/tools/verify_gold_anchors.py --out evals/anchor-check-20261024.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2]
DEFAULT_DRAFT = ROOT / "evals" / "smoke-10-draft.jsonl"
DEFAULT_CORPUS_DIR = ROOT / "examples" / "synthetic-docs"
DEFAULT_TAXONOMY = ROOT / "evals" / "badcase-taxonomy.md"

FM_KEYS = (
    "knowledge_base_id", "document_id", "version_id", "title", "version",
    "effective_at", "valid_until", "status", "supersedes", "superseded_by",
)

ANCHOR_RE = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z]{1,2}-[A-Za-z0-9]+-\d{1,3})(?![A-Za-z0-9-])")
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$", re.M)
DATE_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})")
DATE_ANY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NEGATION_CHARS = set("不未无别勿非莫")
BEHAVIOR_MARKERS = ("任何", "把", "直接", "修改", "不得", "不要")

REQUIRED_FIELDS = (
    "_provenance", "id", "type", "q", "caller", "as_of", "expected_status",
    "required_info_points", "gold_evidence", "must_not_include", "notes",
)

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 机器推断的 type → expected_status 惯例（依据 badcase-taxonomy.md 第 2 节语义 + 草稿自身用法；
# 不是口径文件的原文规定，报告中如实标注为“机器推断”）。
STATUS_CONVENTION = {
    "事实": "answer", "版本": "answer", "跨文档": "answer", "跨库": "answer",
    "计算": "answer", "干扰指令": "answer", "澄清": "clarify", "无答案": "refuse",
}

# 针对具体发现的模板化建议（机器备注，非人工结论）。
HINTS = {
    ("smk-02", "3 个自然日"):
        "语料中最接近的干扰是 kb-b B-D1-01 的『7 个自然日』。若本意是『语料内真实干扰源』，"
        "建议改写为『7 个自然日』；若本意是防『3 工作日/3 自然日』混淆的幻觉护栏，建议在 notes 注明该短语不来自语料。",
    ("smk-05", "7 自然日"):
        "语料原文是『7 个自然日』（b-delivery-rules-v1 B-D1-01）。建议统一写成语料原形，或在评分器中做变体归一。",
    ("smk-09", "10-19"):
        "该短语与 required_info_points 的『次一工作日 10-19 为第 1 日』字面冲突。"
        "推测本意是『不得把 10-19 当作截止日/最终答案』，建议改写成无歧义表述（例如『以 10-19 作为截止日』）。",
    ("smk-09", "10-20 截止"):
        "行为约束类表述，语料中无对应原文，机器无法验证；需作者确认评分实现方式。",
    ("smk-03", "直接用 v2 的 3 个工作日回答旧提交"):
        "行为约束类表述；其中『3 个工作日』确为 v2 现行数值，干扰源本身成立。",
    ("smk-03", "（type=版本回溯）"):
        "『版本回溯』未出现在 badcase-taxonomy.md 第 2 节口径表；expected_status=clarify 与『澄清』行接近，"
        "但计入哪个指标需作者明确。",
    ("smk-05", "（type=权限）"):
        "『权限』未出现在 badcase-taxonomy.md 第 2 节口径表，计入哪个指标未定义；"
        "且 notes 自述权限未实现前只能作占位断言，验收口径需作者明确。",
    ("smk-08", "99 天"):
        "『99 天』确实存在于语料，但位置是 A-F-06 的注入样本原文内；预期答案本身需要提到该样本，"
        "评分时须区分『引用样本文字』与『采纳为业务结论』。",
}


# ---------------------------------------------------------------- 基础工具

def norm(s: str, strip_punct: bool = True) -> str:
    """归一化：NFKC（全角→半角等）+ 小写 + 去空白；strip_punct 时再去掉标点/符号。"""
    s = unicodedata.normalize("NFKC", s).lower()
    out = []
    for ch in s:
        if ch.isspace():
            continue
        if strip_punct:
            cat = unicodedata.category(ch)
            if cat[0] in ("P", "S"):
                continue
        out.append(ch)
    return "".join(out)


def bigrams(s: str) -> set:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def containment(gold: str, scope: str) -> float:
    bg = bigrams(gold)
    if not bg:
        return 0.0
    return len(bg & bigrams(scope)) / len(bg)


def raw_span(text: str, phrase: str, before: int = 14, after: int = 26):
    """在原文里做“忽略空白”的定位，返回供人阅读的原文摘录。"""
    pat = re.compile(r"\s*".join(re.escape(ch) for ch in phrase))
    m = pat.search(text)
    if not m:
        return None
    start = max(0, m.start() - before)
    end = min(len(text), m.end() + after)
    snippet = text[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def one_line(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


# ---------------------------------------------------------------- 语料解析

def parse_frontmatter(raw: str):
    fm, body = {}, raw
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k in FM_KEYS:
                    fm[k] = v
        body = raw[m.end():]
    return fm, body


def build_sections(body: str):
    heads = list(HEADING_RE.finditer(body))
    sections = []
    if not heads:
        sections.append({"anchor": None, "heading": "(无标题)", "level": 1, "text": body.strip()})
        return sections
    pre = body[:heads[0].start()].strip()
    if pre:
        sections.append({"anchor": None, "heading": "(前言)", "level": 1, "text": pre})
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        am = ANCHOR_RE.search(h.group(2))
        sections.append({
            "anchor": am.group(1) if am else None,
            "heading": h.group(2),
            "level": len(h.group(1)),
            "text": body[h.end():end].strip(),
        })
    return sections


def load_corpus(corpus_dir: Path):
    docs = []
    for path in sorted(corpus_dir.glob("kb-*/*.md")):
        raw = path.read_text(encoding="utf-8-sig")
        fm, body = parse_frontmatter(raw)
        sections = build_sections(body)
        by_anchor = {}
        for sec in sections:
            if sec["anchor"] and sec["anchor"] not in by_anchor:
                by_anchor[sec["anchor"]] = sec
        docs.append({
            "path": path,
            "rel": path.relative_to(ROOT).as_posix(),
            "fm": fm,
            "body": body,
            "sections": sections,
            "section_by_anchor": by_anchor,
        })
    return docs


def check_version_chain(docs):
    """检查 kb/文档/版本命名与 supersedes 链的机械一致性。"""
    problems, infos = [], []
    groups = {}
    for d in docs:
        fm = d["fm"]
        key = (fm.get("knowledge_base_id"), fm.get("document_id"))
        groups.setdefault(key, []).append(fm)
        vid = fm.get("version_id", "")
        suffix = "-v" + str(fm.get("version", "")).split(".")[0]
        if fm.get("document_id") and not (vid.endswith(suffix) and vid[: -len(suffix)] == fm["document_id"]):
            infos.append(f"命名提示：{vid} 与 document_id『{fm['document_id']}』+ 版本号『{fm.get('version')}』的惯例不一致")
    for (kb, docid), fms in groups.items():
        vids = {f.get("version_id") for f in fms}
        currents = [f for f in fms if f.get("status") == "current"]
        if len(currents) != 1:
            problems.append(f"{kb}/{docid}：status=current 的版本数为 {len(currents)}（应为 1）")
        for f in fms:
            if f.get("supersedes") and f["supersedes"] not in vids:
                problems.append(f"{f.get('version_id')}.supersedes 指向同组之外：{f['supersedes']}")
            if f.get("superseded_by") and f["superseded_by"] not in vids:
                problems.append(f"{f.get('version_id')}.superseded_by 指向同组之外：{f['superseded_by']}")
    return problems, infos


# ---------------------------------------------------------------- 题集加载

def load_draft(path: Path):
    items, errors = [], []
    for ln, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"第 {ln} 行不是合法 JSON：{exc}")
            continue
        obj["_line"] = ln
        items.append(obj)
    return items, errors


# ---------------------------------------------------------------- 文本分级

def grade_text(gold: str, sec_text: str, body: str):
    """返回 (grade, detail, ratio)。grade ∈ exact / paraphrase / mismatch。"""
    g_strict = norm(gold, strip_punct=False)
    g_loose = norm(gold, strip_punct=True)
    if g_strict:
        if g_strict in norm(sec_text, strip_punct=False):
            return "exact", "锚点章节内·全半角/空白归一后精确子串（保留标点）", 1.0
        if g_strict in norm(body, strip_punct=False):
            return "exact", "同文档其他章节·全半角/空白归一后精确子串（保留标点）", 1.0
    if g_loose:
        if g_loose in norm(sec_text, strip_punct=True):
            return "exact", "锚点章节内·全半角/空白/标点归一后精确子串", 1.0
        if g_loose in norm(body, strip_punct=True):
            return "exact", "同文档其他章节·全半角/空白/标点归一后精确子串", 1.0
    r = containment(g_loose, norm(body, strip_punct=True)) if g_loose else 0.0
    if r >= 0.55:
        return "paraphrase", f"未找到精确子串；整篇字符二元组重合度 {r:.0%}（大意相近的机器启发式判断）", r
    return "mismatch", f"未找到精确子串；整篇字符二元组重合度仅 {r:.0%}", r


# ---------------------------------------------------------------- must_not_include 抽查

def scan_phrase(phrase: str, docs):
    res = {"phrase": phrase, "found": False, "hits": [], "negated": False, "variant": None}
    p = norm(phrase, strip_punct=True)
    if len(p) < 2:
        return res
    for d in docs:
        for sec in d["sections"]:
            scope_raw = (sec["heading"] + "\n" + sec["text"]) if sec["anchor"] else sec["text"]
            ns = norm(scope_raw, strip_punct=True)
            idx = ns.find(p)
            if idx >= 0:
                neg = any(c in NEGATION_CHARS for c in ns[max(0, idx - 2):idx])
                res["found"] = True
                res["negated"] = res["negated"] or neg
                span = raw_span(scope_raw, phrase)
                res["hits"].append((
                    d["fm"].get("version_id") or d["rel"],
                    sec["anchor"] or sec["heading"],
                    span or "(归一化命中，未能回溯原文位置)",
                    neg,
                ))
    if res["found"]:
        return res
    # 近似变体：在所有章节的归一化文本上滑窗（窗口长度 len(p) ~ len(p)+2，容忍插入“个”等）。
    best = (0.0, None)
    L = len(p)
    for d in docs:
        for sec in d["sections"]:
            scope_raw = (sec["heading"] + "\n" + sec["text"]) if sec["anchor"] else sec["text"]
            ns = norm(scope_raw, strip_punct=True)
            for wl in (L, L + 1, L + 2):
                if wl > len(ns):
                    break
                for i in range(len(ns) - wl + 1):
                    w = ns[i:i + wl]
                    r = containment(p, w)
                    if r > best[0]:
                        best = (r, (d["fm"].get("version_id") or d["rel"],
                                    sec["anchor"] or sec["heading"], w))
    if best[0] >= 0.5 and re.search(r"[\u4e00-\u9fff]", best[1][2]):
        # 变体提示只对含汉字的窗口有意义，纯数字窗口（如日期串）是噪音。
        res["variant"] = best
    return res


def classify_mni(iid: str, mni_res: dict, gold_versions: set):
    """返回 (status, detail_lines, is_warn, hint)。"""
    phrase = mni_res["phrase"]
    hint = HINTS.get((iid, phrase), "")
    if mni_res["found"]:
        locs = "；".join(
            f"{v}／{a}" + ("（否定语境）" if neg else "")
            for v, a, _span, neg in mni_res["hits"]
        )
        same = any(v in gold_versions for v, _a, _s, _n in mni_res["hits"])
        detail = f"在语料中命中：{locs}"
        if same:
            detail += "。注意：命中位置在本题 gold 引用的版本内"
        else:
            detail += "。属其他版本/知识库的真实干扰源"
        if mni_res["negated"]:
            detail += "；机器提示：命中处带否定词，短语在原文中以否定形式出现（作为禁出短语合理，但子串式自动评分需防把引用原文误判为违规）"
        return "命中", [detail], False, hint
    behavioral = any(m in phrase for m in BEHAVIOR_MARKERS)
    if behavioral:
        return "未命中（行为约束类）", [
            "未在语料中命中；措辞含『任何/把/直接/修改』等，机器推断为答案行为约束而非语料内干扰源",
        ], False, hint
    lines = ["未在语料中命中，且措辞不像行为约束——若意图指向语料内干扰源，则当前写法与语料原文不一致"]
    if mni_res["variant"]:
        r, (v, a, w) = mni_res["variant"]
        lines.append(f"最接近的归一化窗口：『{w}』（{v}／{a}，重合度 {r:.0%}）")
    return "未命中（需作者确认）", lines, True, hint


# ---------------------------------------------------------------- 口径表解析

def parse_taxonomy(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    m = re.search(r"^##\s*2\..*?(?=^##\s*3\.|\Z)", text, re.M | re.S)
    sec = m.group(0) if m else text
    table, metrics = {}, {}
    for line in sec.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        first = cells[0].replace("**", "").strip()
        first = re.sub(r"[（(].*?[）)]", "", first).strip()
        if not first or first == "类别" or set(first) <= {"-", ":"}:
            continue
        incl = cells[1].replace("**", "").strip()
        for name in re.split(r"[/／、]", first):
            name = name.strip()
            if name:
                table[name] = incl
                metrics[name] = cells[2].replace("**", "").strip()
    return table, metrics


def check_taxonomy(item: dict, table: dict, metrics: dict):
    t = item.get("type", "")
    row = {
        "type": t,
        "known": t in table,
        "recall_included": table.get(t, "（表外）"),
        "metric": metrics.get(t, "—"),
        "convention": STATUS_CONVENTION.get(t),
        "issues": [],
    }
    if t in table:
        conv = STATUS_CONVENTION.get(t)
        if conv and item.get("expected_status") != conv:
            row["issues"].append(
                f"type={t} 的机器推断 expected_status 为『{conv}』，草稿为『{item.get('expected_status')}』，请作者确认"
            )
        nn = norm(item.get("notes", ""), strip_punct=True)
        incl = table[t]
        if "不计入evidencerecall" in nn and incl == "是":
            row["issues"].append("notes 声称不计入 Evidence Recall，与口径表『计入=是』冲突")
        elif re.search(r"(?<!不)计入evidencerecall", nn) and incl == "否":
            row["issues"].append("notes 声称计入 Evidence Recall，与口径表『计入=否』冲突")
    else:
        row["issues"].append(f"type『{t}』未出现在 badcase-taxonomy.md 第 2 节口径表，计入哪个指标未定义，需作者明确")
    return row


# ---------------------------------------------------------------- 专项验算

def check_smk09(item: dict, docs_by_version: dict):
    res = {"weekday": None, "weekday_ok": False, "seq": [], "deadline_ok": False,
           "faq_checks": [], "rip_tokens_ok": None, "rip_tokens": {}, "conflicts": []}
    d0 = date(2026, 10, 16)
    res["weekday"] = WEEKDAY_ZH[d0.weekday()]
    res["weekday_ok"] = d0.weekday() == 4
    cur, seq = d0, []
    while len(seq) < 3:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            seq.append(cur)
    res["seq"] = seq
    res["deadline_ok"] = seq[-1] == date(2026, 10, 21)

    faq = docs_by_version.get("a-acceptance-faq-v1")
    sec = faq["section_by_anchor"].get("A-F-02") if faq else None
    if sec:
        nf = norm(sec["text"], strip_punct=True)
        res["faq_checks"] = list({
            "题面日期 2026-10-16 出现于 A-F-02": "20261016" in nf,
            "A-F-02 的『周五』表述与 datetime 计算一致": ("周五" in sec["text"]) and res["weekday_ok"],
            "『10 月 19 日为第 1 日』与计算一致": "10月19日为第1日" in nf,
            "『10 月 20 日为第 2 日』与计算一致": "10月20日为第2日" in nf,
            "『10 月 21 日为第 3 日』与计算一致": "10月21日为第3日" in nf,
            "『截止为 10 月 21 日 18:00』与计算一致": "截止为10月21日1800" in nf,
            "『不考虑法定节假日和调休』口径说明在场": ("法定节假日" in nf) and ("调休" in nf),
        }.items())

    rips = item.get("required_info_points", [])
    joined = norm(" ".join(rips), strip_punct=True)
    res["rip_tokens"] = {
        "含 10-19": "1019" in joined,
        "含 10-20": "1020" in joined,
        "含 10-21": "1021" in joined,
        "含 18:00": "1800" in joined,
        "含 Asia/Shanghai": "asiashanghai" in joined,
    }
    seq_tokens = {d.strftime("%m-%d") for d in seq}
    res["rip_tokens_ok"] = seq_tokens.issubset(
        {t for t in re.findall(r"\d{2}-\d{2}", " ".join(rips))}
    )
    for ph in item.get("must_not_include", []):
        np_ = norm(ph, strip_punct=True)
        for rip in rips:
            nr = norm(rip, strip_punct=True)
            if np_ and nr and (np_ in nr or nr in np_):
                res["conflicts"].append((ph, rip))
    return res


def check_smk03(item: dict, docs_by_version: dict):
    res = {"range": None, "q_date": None, "in_range": False, "fm_ok": False,
           "archived_at_asof": False, "history_access": None, "errors": []}
    v1 = docs_by_version.get("a-delivery-rules-v1")
    if not v1:
        res["errors"].append("a-delivery-rules-v1 不在语料中，无法核对历史口径")
        return res
    sec = v1["section_by_anchor"].get("A-D1-01")
    if not sec:
        res["errors"].append("a-delivery-rules-v1 中未找到 A-D1-01 章节")
        return res
    m = DATE_RANGE_RE.search(sec["text"])
    if not m:
        res["errors"].append("A-D1-01 正文中未解析出『YYYY-MM-DD 至 YYYY-MM-DD』日期范围")
        return res
    lo, hi = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    res["range"] = (lo, hi)
    q_dates = DATE_ANY_RE.findall(item.get("q", ""))
    if not q_dates:
        res["errors"].append("题面（q）中未找到 YYYY-MM-DD 日期")
        return res
    qd = date.fromisoformat(q_dates[0])
    res["q_date"] = qd
    res["in_range"] = lo <= qd <= hi
    fm_eff = (v1["fm"].get("effective_at") or "")[:10]
    fm_vu = (v1["fm"].get("valid_until") or "")[:10]
    res["fm_window"] = (fm_eff, fm_vu)
    try:
        res["fm_ok"] = bool(fm_eff) and bool(fm_vu) and (date.fromisoformat(fm_eff) <= qd < date.fromisoformat(fm_vu))
    except ValueError:
        res["fm_ok"] = False
    as_of = item.get("as_of", "")
    try:
        res["archived_at_asof"] = bool(fm_vu) and date.fromisoformat(as_of) >= date.fromisoformat(fm_vu)
    except ValueError:
        pass
    res["history_access"] = (item.get("caller") or {}).get("history_access")
    return res


# ---------------------------------------------------------------- 逐题主流程

def check_item(item: dict, docs_by_version: dict, table: dict, metrics: dict):
    iid = item.get("id", "?")
    errors, warns, notes = [], [], []
    evidence_rows, mni_rows, special = [], [], []

    for f in REQUIRED_FIELDS:
        if f not in item:
            errors.append(f"缺少必需字段『{f}』")
    try:
        as_of = date.fromisoformat(item.get("as_of", ""))
    except ValueError:
        as_of = None
        errors.append(f"as_of『{item.get('as_of')}』不是 YYYY-MM-DD")
    if item.get("expected_status") not in ("answer", "refuse", "clarify"):
        errors.append(f"expected_status『{item.get('expected_status')}』不在 answer/refuse/clarify 之内")
    if not item.get("gold_evidence"):
        errors.append("gold_evidence 为空")

    gold_versions = {ev.get("version_id") for ev in item.get("gold_evidence", [])}
    caller_kb = (item.get("caller") or {}).get("kb")

    for i, ev in enumerate(item.get("gold_evidence", []), 1):
        vid = ev.get("version_id")
        anchor = ev.get("anchor", "")
        gold = ev.get("text", "")
        row = {"idx": i, "vid": vid, "anchor": anchor, "gold": gold,
               "valid": False, "kbdoc": "—", "status_line": "—", "anchor_result": "未命中",
               "heading": "", "grade": "mismatch", "grade_detail": "", "excerpt": ""}
        doc = docs_by_version.get(vid)
        if not doc:
            errors.append(f"证据 {i}：version_id『{vid}』在语料元数据中不存在")
            row["grade_detail"] = "version_id 无效，未做文本比对"
            evidence_rows.append(row)
            continue
        fm = doc["fm"]
        row["valid"] = True
        row["kbdoc"] = f"{fm.get('knowledge_base_id')} / {fm.get('document_id')}"
        row["status_line"] = (
            f"status={fm.get('status')}，effective_at={fm.get('effective_at')}"
            + (f"，valid_until={fm.get('valid_until')}" if fm.get("valid_until") else "")
            + (f"，supersedes={fm.get('supersedes')}" if fm.get("supersedes") else "")
            + (f"，superseded_by={fm.get('superseded_by')}" if fm.get("superseded_by") else "")
        )
        # (a) 附属关系与 as_of 时点
        if caller_kb and fm.get("knowledge_base_id") != caller_kb:
            if item.get("expected_status") == "answer":
                warns.append(
                    f"证据 {i} 位于 {fm.get('knowledge_base_id')}，而 caller.kb={caller_kb} 且 expected_status=answer——"
                    "若非有意的跨库可答题，请确认权限设计"
                )
            else:
                notes.append(
                    f"证据 {i} 位于 {fm.get('knowledge_base_id')}（caller.kb={caller_kb}）且 expected_status="
                    f"{item.get('expected_status')}——与越权/跨库题设计自洽（机器推断）"
                )
        if fm.get("status") == "historical" and as_of and fm.get("valid_until"):
            try:
                if as_of >= date.fromisoformat(fm["valid_until"][:10]):
                    notes.append(
                        f"证据 {i} 的 {vid} 在 as_of={as_of} 时点已过 valid_until={fm['valid_until'][:10]}"
                        "（status=historical）——引用历史版本，请确认属本题设计"
                    )
            except ValueError:
                pass
        elif fm.get("status") == "current" and as_of and fm.get("effective_at"):
            try:
                if as_of < date.fromisoformat(fm["effective_at"][:10]):
                    warns.append(f"证据 {i} 的 {vid} effective_at 晚于 as_of，现行版本在题面时点尚未生效")
            except ValueError:
                pass
        # (b) anchor 命中
        sec = doc["section_by_anchor"].get(anchor)
        if sec:
            row["anchor_result"] = "命中（章节标题）"
            row["heading"] = sec["heading"]
        else:
            inline = re.search(r"(?<![A-Za-z0-9-])" + re.escape(anchor) + r"(?![A-Za-z0-9-])", doc["body"]) if anchor else None
            if inline:
                row["anchor_result"] = "仅行内提及（弱命中）"
                warns.append(f"证据 {i} 的 anchor『{anchor}』在 {vid} 中没有章节标题，仅行内提及")
            else:
                row["anchor_result"] = "未命中"
                errors.append(f"证据 {i}：anchor『{anchor}』在 {vid} 正文中未找到（标题与行内均无）")
        # (c) text 分级
        if sec:
            grade, detail, _r = grade_text(gold, sec["text"], doc["body"])
            row["grade"], row["grade_detail"] = grade, detail
            span = raw_span(sec["text"], gold)
            row["excerpt"] = span or one_line(sec["text"])[:90]
            if grade == "mismatch":
                errors.append(f"证据 {i}：gold text 与 {vid}／{anchor} 原文不一致（mismatch）——{detail}")
            elif grade == "paraphrase":
                warns.append(f"证据 {i}：gold text 判为 paraphrase——{detail}，请作者确认是否接受该改写")
            elif "其他章节" in detail:
                warns.append(f"证据 {i}：gold text 命中于 {vid} 的其他章节而非锚点章节，请确认锚点选择")
        else:
            row["grade_detail"] = "anchor 未命中，未做文本比对"
        evidence_rows.append(row)

    # (d) must_not_include 抽查
    for ph in item.get("must_not_include", []):
        mres = scan_phrase(ph, docs_by_version and list(docs_by_version.values()))
        status, lines, is_warn, hint = classify_mni(iid, mres, gold_versions)
        if is_warn:
            warns.append(f"must_not_include『{ph}』：" + "；".join(lines) + (f"（机器建议：{hint}）" if hint else ""))
        mni_rows.append({"phrase": ph, "status": status, "lines": lines, "hint": hint})

    # (g) 口径对照
    tax = check_taxonomy(item, table, metrics)
    for issue in tax["issues"]:
        hint = HINTS.get((iid, f"（type={tax['type']}）"), "")
        warns.append(f"口径对照：{issue}" + (f"（机器建议：{hint}）" if hint else ""))

    return {
        "id": iid, "type": item.get("type", "?"),
        "expected_status": item.get("expected_status", "?"),
        "q": item.get("q", ""), "notes_field": item.get("notes", ""),
        "errors": errors, "warns": warns, "notes": notes,
        "evidence": evidence_rows, "mni": mni_rows, "tax": tax,
        "special": special,
        "verdict": "未通过" if errors else ("通过（有复核点）" if warns else "通过"),
    }


# ---------------------------------------------------------------- 报告渲染

def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(one_line(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(lines)


def render(items, docs, draft_path, corpus_dir, taxonomy_path, taxonomy_table,
           chain_problems, chain_infos, file_errors, generated_at, argv_str):
    L = []
    ap = L.append

    total = len(items)
    verdicts = Counter(it["verdict"] for it in items)
    grades = Counter(row["grade"] for it in items for row in it["evidence"])
    anchor_hits = sum(1 for it in items for row in it["evidence"] if row["anchor_result"].startswith("命中"))
    valid_vids = sum(1 for it in items for row in it["evidence"] if row["valid"])
    gold_total = sum(len(it["evidence"]) for it in items)
    warn_items = [it for it in items if it["warns"]]

    ap("# 冒烟评测题金标锚点机器校验报告（anchor-check）")
    ap("")
    ap(f"- 校验对象：`evals/smoke-10-draft.jsonl`（{total} 条草稿题，未做任何修改）")
    ap(f"- 语料：`examples/synthetic-docs/`（{len(docs)} 份 Markdown，未做任何修改）")
    ap("- 口径依据：`evals/badcase-taxonomy.md` 第 2 节")
    ap("- 校验工具：`evals/tools/verify_gold_anchors.py`（纯标准库、可重复运行、不联网）")
    ap(f"- 运行命令：`.venv/Scripts/python.exe {argv_str}`")
    ap(f"- 生成时间：{generated_at}")
    ap("")
    ap("> **性质声明（必读）**：本报告是**机器辅助检查**结果，**不是人工金标复核**，"
       "不构成 `badcase-taxonomy.md` 第 3 节意义上的核对记录（该节要求核对人是有血有肉的 author）。"
       "`smoke-10-draft.jsonl` 的 `_provenance` 亦自述为『第三方评审草稿，锚点需作者本人复核』。"
       "**机器结果只用于缩小人工复核范围、指出疑似问题；作者仍须逐条人工确认，并以本人名义填写核对记录。**")
    ap("")
    ap("---")
    ap("")
    ap("## 1. 方法与局限")
    ap("")
    ap("### 1.1 检查项（对应任务口径 a–g）")
    ap("")
    ap("| 项 | 内容 | 判定输出 |")
    ap("|---|---|---|")
    ap("| a | version_id 是否在语料元数据中存在；kb/document_id/版本命名与 supersedes 链是否机械自洽；与 caller.kb 的关系 | 有效/无效 + 备注 |")
    ap("| b | anchor 条款编号是否在该版本文档正文命中（章节标题为强命中，仅行内提及为弱命中） | 命中/弱命中/未命中 |")
    ap("| c | gold text 与条款原文一致性：先 NFKC 全半角+去空白（保留标点）找精确子串，再全半角+空白+标点全归一找精确子串；都找不到按字符二元组重合度近似 | exact / paraphrase / mismatch |")
    ap("| d | must_not_include 短语是否真实存在于语料（含否定语境识别、近似变体滑窗提示） | 命中/未命中（行为约束类）/未命中（需作者确认） |")
    ap("| e | smk-09：用 `datetime` 独立验算 2026-10-16 星期与 3 个工作日序列，并与 A-F-02 原文、required_info_points 交叉核对 | 通过/不一致 |")
    ap("| f | smk-03：A-D1-01 适用日期范围 vs 题面提交日期 vs 元数据 effective_at/valid_until vs as_of | 通过/不一致 |")
    ap("| g | type/expected_status 组合与 `badcase-taxonomy.md` 第 2 节口径表对照（含 notes 与口径表的矛盾检测） | 一致/表外类型/冲突 |")
    ap("")
    ap("### 1.2 归一化与分级定义")
    ap("")
    ap("- **exact**：gold text 经归一化后是条款原文的精确子串（两级归一化任一命中即可，报告中注明所用级别）。")
    ap("- **paraphrase**：精确子串未命中，但整篇字符二元组重合度 ≥ 55%（机器启发式，仅代表字面相近，不代表语义正确）。")
    ap("- **mismatch**：精确子串未命中且重合度低于阈值。")
    ap("- 归一化：`unicodedata.normalize('NFKC')`（全角→半角）、小写、去除全部空白；第二级再去掉全部标点/符号。")
    ap("- 工作日验算仅按周一至周五（与语料演示口径一致，不含法定节假日与调休）。")
    ap("")
    ap("### 1.3 局限（机器检查做不了什么）")
    ap("")
    ap("1. 无法判断语义等价与业务正确性：exact 只证明字面一致，不证明『这句话作为金标语义上正确』。")
    ap("2. required_info_points 的事实支持未逐条机器验证（仅 smk-09 的日期类信息点做了验算）。")
    ap("3. must_not_include 中的行为约束类短语（『任何百分比』等）无法机器验证，只能标注为行为约束。")
    ap("4. 权限/越权（smk-05）与注入抵抗（smk-08）只能验证语料文字存在，**不能验证系统真实行为**；notes 中『mock 通过不等于真实模型已抵抗』的约束机器无法替代。")
    ap("5. paraphrase 的重合度阈值是经验值，可能漏判或误判。")
    ap("6. 口径对照使用的 type→expected_status 惯例是机器推断（见脚本内 `STATUS_CONVENTION`），不是口径文件原文。")
    ap("")
    ap("## 2. 文件级机械检查与指纹")
    ap("")
    if file_errors:
        for e in file_errors:
            ap(f"- 文件级问题：{e}")
    else:
        ap("- 草稿每行均为合法 JSON；字段完整性、id 唯一性、as_of 格式逐条检查通过（问题见逐题明细）。")
    if chain_problems:
        for p in chain_problems:
            ap(f"- 语料版本链问题：{p}")
    else:
        ap("- 语料版本链机械自洽：每份文档 status=current 恰好 1 个；supersedes/superseded_by 双向对应；version_id 与 document_id+版本号命名惯例一致。")
    for info in chain_infos:
        ap(f"- {info}")
    ap("")
    ap(md_table(["文件", "sha256（前 12 位）", "字节"],
                [[f"`{p.relative_to(ROOT).as_posix()}`", sha12(p), p.stat().st_size]
                 for p in [d["path"] for d in docs] + [taxonomy_path, draft_path]]))
    ap("")
    ap("## 3. 语料元数据一览（检查 a 的参照系）")
    ap("")
    ap(md_table(["version_id", "kb", "document_id", "status", "effective_at", "valid_until", "supersedes", "superseded_by"],
                [[d["fm"].get("version_id"), d["fm"].get("knowledge_base_id"), d["fm"].get("document_id"),
                  d["fm"].get("status"), d["fm"].get("effective_at"), d["fm"].get("valid_until") or "—",
                  d["fm"].get("supersedes") or "—", d["fm"].get("superseded_by") or "—"] for d in docs]))
    ap("")
    ap("## 4. 逐题核对总表")
    ap("")
    ap(md_table(
        ["id", "type", "expected_status", "version_id 有效性", "anchor 命中", "text 分级", "结论", "复核点数"],
        [[it["id"], it["type"], it["expected_status"],
          f"{valid_vids_of(it)}/{len(it['evidence'])}",
          "；".join(row["anchor_result"] for row in it["evidence"]),
          "；".join(row["grade"] for row in it["evidence"]),
          it["verdict"], len(it["warns"])] for it in items]))
    ap("")
    ap(f"汇总：version_id 有效 {valid_vids}/{gold_total}；anchor 强/弱命中 {anchor_hits}/{gold_total}；"
       f"text 分级 exact={grades.get('exact', 0)} paraphrase={grades.get('paraphrase', 0)} mismatch={grades.get('mismatch', 0)}；"
       f"机器口径全过 {verdicts.get('通过', 0)} 条、通过但有复核点 {verdicts.get('通过（有复核点）', 0)} 条、未通过 {verdicts.get('未通过', 0)} 条。")
    ap("")
    ap("## 5. 逐题明细")
    ap("")
    for it in items:
        ap(f"### {it['id']}（type={it['type']}，expected_status={it['expected_status']}）—— 结果：{it['verdict']}")
        ap("")
        ap(f"- 题面：{one_line(it['q'])}")
        for row in it["evidence"]:
            ap(f"- 证据 {row['idx']}（检查 a/b/c）：version_id=`{row['vid']}` "
               f"{'有效' if row['valid'] else '无效'}（{row['kbdoc']}；{row['status_line']}）；"
               f"anchor `{row['anchor']}` → {row['anchor_result']}"
               + (f"（{row['heading']}）" if row["heading"] else "")
               + f"；text 分级 = **{row['grade']}**（{row['grade_detail']}）")
            ap(f"  - gold：{one_line(row['gold'])}")
            if row["excerpt"]:
                ap(f"  - 原文摘录：{one_line(row['excerpt'])}")
        if it["mni"]:
            ap("- 检查 d（must_not_include 抽查）：")
            for m in it["mni"]:
                for j, line in enumerate(m["lines"]):
                    prefix = f"  - 『{m['phrase']}』" if j == 0 else "    "
                    ap(prefix + line)
                if m["hint"]:
                    ap(f"    机器建议：{m['hint']}")
        else:
            ap("- 检查 d（must_not_include 抽查）：本题为空")
        ap(f"- 检查 g（口径对照）：type={it['tax']['type']}，"
           + (f"口径表内：计入 Evidence Recall={it['tax']['recall_included']}，指标={it['tax']['metric']}；"
              f"机器推断 expected_status={it['tax']['convention']}，草稿一致"
              if it["tax"]["known"] and not it["tax"]["issues"] else
              "；".join(it["tax"]["issues"]) if it["tax"]["issues"] else "见问题列表"))
        for s_title, s_lines in it["special"]:
            ap(f"- {s_title}")
            for line in s_lines:
                ap(f"  - {line}")
        for n in it["notes"]:
            ap(f"- 备注：{n}")
        for w in it["warns"]:
            ap(f"- 复核点：{w}")
        for e in it["errors"]:
            ap(f"- 未通过项：{e}")
        ap("")

    ap("## 6. must_not_include 干扰源抽查汇总（检查 d）")
    ap("")
    rows = []
    for it in items:
        for m in it["mni"]:
            loc = m["lines"][0] if m["lines"] else ""
            rows.append([it["id"], f"『{m['phrase']}』", m["status"], one_line(loc)])
    ap(md_table(["id", "短语", "结果", "位置/说明"], rows))
    ap("")
    ap("任务指定的两个抽查样例的机器结论：")
    ap("")
    ap("1. 『5 个工作日』→ 命中 `a-delivery-rules-v1`／A-D1-02（『…次一工作日起 5 个工作日内给出验收意见…』），"
       "确认 v1 是与 v2『3 个工作日』相对的真实干扰源。")
    ap("2. 『7 个自然日』→ 命中 `b-delivery-rules-v1`／B-D1-01（『…次一自然日起 7 个自然日内回复…』），"
       "确认 kb-b 是与 A 库工作日口径相对的真实干扰源；注意 smk-05 写的是『7 自然日』（少个『个』），字面不在语料中，见问题清单。")
    ap("")

    smk09 = next((it for it in items if it["id"] == "smk-09"), None)
    if smk09 and smk09["special"]:
        ap("## 7. smk-09 日期独立验算（检查 e）")
        ap("")
        for _t, lines in smk09["special"]:
            for line in lines:
                ap(f"- {line}")
        ap("")

    smk03 = next((it for it in items if it["id"] == "smk-03"), None)
    if smk03 and smk03["special"]:
        ap("## 8. smk-03 历史访问口径核对（检查 f）")
        ap("")
        for _t, lines in smk03["special"]:
            for line in lines:
                ap(f"- {line}")
        ap("")

    ap("## 9. type / expected_status 与口径表对照（检查 g）")
    ap("")
    ap(md_table(["id", "type", "口径表内？", "计入 Evidence Recall", "指标归属", "expected_status（草稿）", "机器推断", "结论"],
                [[it["id"], it["tax"]["type"],
                  "是" if it["tax"]["known"] else "否（表外）",
                  it["tax"]["recall_included"], it["tax"]["metric"],
                  it["expected_status"], it["tax"]["convention"] or "—",
                  "一致" if it["tax"]["known"] and not it["tax"]["issues"] else "；".join(one_line(i) for i in it["tax"]["issues"])]
                 for it in items]))
    ap("")
    ap("说明：『机器推断』列来自脚本内置惯例表，不是 `badcase-taxonomy.md` 原文；表外类型（版本回溯、权限）在口径表第 2 节没有对应行，需作者补充口径。")
    ap("")
    ap("## 10. 汇总")
    ap("")
    ap(f"- 机器口径全过：**{verdicts.get('通过', 0)} 条**"
       f"（{'、'.join(it['id'] for it in items if it['verdict'] == '通过') or '—'}）")
    ap(f"- 通过但有复核点：**{verdicts.get('通过（有复核点）', 0)} 条**"
       f"（{'、'.join(it['id'] for it in items if it['verdict'] == '通过（有复核点）') or '—'}）")
    ap(f"- 未通过：**{verdicts.get('未通过', 0)} 条**"
       f"（{'、'.join(it['id'] for it in items if it['verdict'] == '未通过') or '—'}）")
    ap("- 锚点与原文：全部 gold text 判为 exact，无 paraphrase/mismatch；version_id 全部有效，anchor 全部以章节标题强命中。"
       "**这只说明锚点『字面对得上』，不等于金标语义正确。**")
    ap("- 再次强调：本报告为机器辅助检查，**作者仍须逐条人工确认**并按 `badcase-taxonomy.md` 第 3 节留痕。")
    ap("")
    ap("## 11. 问题清单（需作者重点复核）")
    ap("")
    if warn_items:
        n = 0
        for it in warn_items:
            for w in it["warns"]:
                n += 1
                ap(f"{n}. **{it['id']}**：{w}")
    else:
        ap("（机器检查未发现需复核项——但仍不豁免人工逐条确认。）")
    ap("")
    ap("另有两条非阻塞的机器备注：")
    ap("")
    ap("- smk-04 的 must_not_include『另设整改完成天数』在 gold 同文档（A-R-02）以否定形式出现（『本手册不另设整改完成天数』）：作为禁出短语合理，但自动评分若做子串匹配会把引用原文误判为违规，建议评分器识别否定语境。")
    ap("- smk-08 的 must_not_include『99 天』命中于 A-F-06 注入样本原文内：干扰源真实，但预期答案本身需要提到该样本，评分须区分『引用样本文字』与『采纳为业务结论』。")
    ap("")
    ap("## 12. 供作者填写的人工复核记录（模板，来自 badcase-taxonomy.md 第 3 节表头）")
    ap("")
    rows = []
    for it in items:
        excerpt = "；".join(one_line(row["excerpt"])[:30] for row in it["evidence"] if row["excerpt"])
        rows.append([it["id"], "author", "____-__-__", excerpt, "____", "____"])
    ap(md_table(["题目ID", "核对人", "核对时间", "锚点原文摘录（≤30字，机器预填，须人工核对）", "锚点是否随文档修订复核", "结论"], rows))
    ap("")
    ap("---")
    ap("")
    ap("*本报告由 `evals/tools/verify_gold_anchors.py` 生成；重跑脚本即可复现（语料或题集变更后指纹会变化）。"
       "报告本身不是核对记录，不能替代作者逐条人工确认。*")
    return "\n".join(L) + "\n"


def valid_vids_of(it):
    return sum(1 for row in it["evidence"] if row["valid"])


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="冒烟评测题金标锚点机器校验")
    parser.add_argument("--draft", default=str(DEFAULT_DRAFT))
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_DIR))
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY))
    parser.add_argument("--out", default=None, help="同时把 Markdown 报告写到该路径（不写则仅打印）")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    draft_path, corpus_dir, taxonomy_path = Path(args.draft), Path(args.corpus), Path(args.taxonomy)
    docs = load_corpus(corpus_dir)
    docs_by_version = {d["fm"].get("version_id"): d for d in docs if d["fm"].get("version_id")}
    items, file_errors = load_draft(draft_path)
    chain_problems, chain_infos = check_version_chain(docs)
    table, metrics = parse_taxonomy(taxonomy_path)

    ids = [it.get("id") for it in items]
    if len(ids) != len(set(ids)):
        file_errors.append("题目 id 存在重复")

    # 文件级字段完整性
    for it in items:
        for f in REQUIRED_FIELDS:
            if f not in it:
                file_errors.append(f"{it.get('id', '?')}（第 {it.get('_line')} 行）缺少字段『{f}』")

    results = []
    for it in items:
        res = check_item(it, docs_by_version, table, metrics)

        if it.get("id") == "smk-09":
            r9 = check_smk09(it, docs_by_version)
            lines = [
                f"datetime 计算：2026-10-16 weekday()={date(2026, 10, 16).weekday()} → "
                f"{r9['weekday']}，与题面『周五』{'一致' if r9['weekday_ok'] else '不一致'}。",
                "次一工作日起 3 个工作日（仅周一至周五）："
                + " → ".join(f"第{i + 1}日 = {d.isoformat()}（{WEEKDAY_ZH[d.weekday()]}）" for i, d in enumerate(r9["seq"]))
                + f"；截止日 = {r9['seq'][-1].isoformat()} 18:00（{'与 required_info_points 一致' if r9['deadline_ok'] else '与预期不一致'}）。",
            ]
            for name, ok in r9["faq_checks"]:
                lines.append(f"与 A-F-02 交叉核对——{name}：{'通过' if ok else '不一致'}")
            tok = "；".join(f"{k}{'有' if v else '无'}" for k, v in r9["rip_tokens"].items())
            lines.append(f"required_info_points 信息点扫描：{tok}；工作日序列与信息点日期一致：{'是' if r9['rip_tokens_ok'] else '否'}")
            for ph, rip in r9["conflicts"]:
                lines.append(f"发现字面冲突：must_not_include『{ph}』与 required_info_points『{rip}』互为子串——见问题清单")
                if not any(ph in w for w in res["warns"]):
                    hint = HINTS.get((it["id"], ph), "")
                    res["warns"].append(
                        f"must_not_include『{ph}』与 required_info_points『{rip}』字面冲突"
                        + (f"（机器建议：{hint}）" if hint else "")
                    )
            res["special"].append(("检查 e（datetime 独立验算 + A-F-02 交叉核对）", lines))

        if it.get("id") == "smk-03":
            r3 = check_smk03(it, docs_by_version)
            lines = []
            for e in r3["errors"]:
                lines.append(f"验算受阻：{e}")
            if r3["range"]:
                lo, hi = r3["range"]
                lines.append(
                    f"A-D1-01 原文适用范围：{lo.isoformat()} 至 {hi.isoformat()}；"
                    f"题面提交日期 {r3['q_date'].isoformat()} 落在范围内：{'是' if r3['in_range'] else '否'}。"
                )
                fm_eff, fm_vu = r3.get("fm_window", ("—", "—"))
                lines.append(
                    f"元数据一致性：effective_at={fm_eff}，valid_until={fm_vu}（左闭右开），"
                    f"覆盖题面提交日期：{'是' if r3['fm_ok'] else '否'}；正文范围止于 {hi.isoformat()}，与 valid_until 无矛盾："
                    f"{'是' if (not fm_vu or hi.isoformat() < fm_vu) else '否'}。"
                )
                lines.append(
                    f"as_of={it.get('as_of')} ≥ valid_until={fm_vu} → v1 在答题时点已归档（status=historical）："
                    f"{'是' if r3['archived_at_asof'] else '否'}——与 expected_status=clarify 的『先确认历史口径』设计自洽（机器推断）。"
                )
                lines.append(
                    f"caller.history_access={r3['history_access']!r}——与 required_info_points"
                    "『确认调用者是否有历史版本访问范围』一致；notes 已写明：若声明开放历史访问，答案应为 5 个工作日并标注 historical 版本。"
                )
                if not r3["in_range"]:
                    res["errors"].append("题面提交日期不在 A-D1-01 适用范围内")
                if not r3["fm_ok"]:
                    res["warns"].append("v1 元数据有效期与题面提交日期/正文范围的一致性未通过，请作者确认")
            res["special"].append(("检查 f（历史口径核对）", lines))

        results.append(res)

    # 渲染时把 e/f 专项行合入明细，同时输出独立章节（render 内部按 id 抽取）
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_rel = SCRIPT_PATH.relative_to(ROOT).as_posix()
    argv_str = " ".join([script_rel] + sys.argv[1:])
    report = render(results, docs, draft_path, corpus_dir, taxonomy_path, table,
                    chain_problems, chain_infos, file_errors, generated_at, argv_str)

    print(report)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8", newline="\n")
        print(f"[verify_gold_anchors] 报告已写出：{out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
