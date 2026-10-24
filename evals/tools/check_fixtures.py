#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_fixtures.py — 用实测复核 examples/format-fixtures 的声称是否属实。

复核对象：
  1) examples/format-fixtures/README.md 第 2 节「已实测事实」；
  2) PROVENANCE.md「标注方式说明」中关于夹具元数据的声明（DOCX 核心属性 / PDF 文档信息）。

方法：pypdf 抽取 PDF 文本与元数据；标准库 zipfile + xml.etree 读 DOCX docProps/core.xml；
     字节级检查 fixture-messy.txt。不联网、不修改任何被检文件。

运行：E:\\AIjob\\gpt\\rag\\.venv\\Scripts\\python.exe evals/tools/check_fixtures.py
退出码：全部通过=0；存在 FAIL=1（fail-loud）。
"""
import hashlib
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from pypdf import PdfReader
except ImportError:
    print("缺少 pypdf，请使用项目 venv 运行", file=sys.stderr)
    sys.exit(2)

BASE = os.path.dirname(os.path.abspath(__file__))            # evals/tools
ROOT = os.path.dirname(os.path.dirname(BASE))                # 仓库根
FIX = os.path.join(ROOT, "examples", "format-fixtures")

RESULTS = []  # (group, 声称, 实测, PASS/FAIL)


def record(group, claimed, actual, ok):
    RESULTS.append((group, claimed, actual, bool(ok)))


def norm(s):
    """去掉所有空白字符，用于页眉/页脚等对空格敏感度低的匹配。"""
    return re.sub(r"\s+", "", s or "")


def l_tokens(t):
    """页面文本中的 L+数字 行号 token 集合。基于保留空白的原文切分：
    去空白文本会把行号与上一行的 A-R-02 粘连，负向断言会全部误判。"""
    return set(re.findall(r"(?<![A-Za-z0-9])L\d+(?![0-9])", t or ""))


MARKERS = ("DeepSeek", "本地模型", "local-model")


def has_marker(v):
    if not v:
        return False
    low = str(v).lower()
    return any(m.lower() in low for m in MARKERS)


# ────────────────────────── a. fixture-table.pdf ──────────────────────────
HEADER_TEXT = "阶段交付与验收规则（A 库）— 合成演示夹具 — 内部编号 FIXTURE-A-001"
FOOTERS = ["第 1 页 / 共 2 页", "第 2 页 / 共 2 页"]
HDR_CELLS = ["分级", "必需材料", "对应处理时限", "依据条款"]


def check_table_pdf():
    g = "fixture-table.pdf"
    path = os.path.join(FIX, "fixture-table.pdf")
    reader = PdfReader(path)
    pages = [p.extract_text() or "" for p in reader.pages]
    page_norms = [norm(t) for t in pages]
    n = len(reader.pages)
    record(g, "共 2 页", f"页数 = {n}", n == 2)

    # 每页字符数：raw（含换行）/ 去换行 / 去所有空白
    stats = []
    for t in pages:
        stats.append((len(t), len(t.replace("\n", "").replace("\r", "")),
                      len(re.sub(r"\s+", "", t))))
    claimed = [1190, 784]
    for i, c in enumerate(claimed):
        raw, nonl, nows = stats[i]
        best = min([("raw", raw), ("去换行", nonl), ("去空白", nows)],
                   key=lambda kv: abs(kv[1] - c))
        ok = abs(best[1] - c) / c <= 0.05
        record(g, f"第 {i+1} 页约 {c} 可抽取字符",
               f"raw={raw} / 去换行={nonl} / 去空白={nows}（最接近口径：{best[0]}）", ok)

    # 页眉逐页
    for i, pn in enumerate(page_norms):
        record(g, f"页眉文字在第 {i+1} 页被抽取",
               "出现" if norm(HEADER_TEXT) in pn else "未出现",
               norm(HEADER_TEXT) in pn)

    # 页脚逐页
    for i, f in enumerate(FOOTERS):
        target = i + 1  # 「第 i+1 页」应在第 i+1 页
        hit = norm(f) in page_norms[target - 1]
        record(g, f"页脚「{f}」在第 {target} 页被抽取",
               "出现" if hit else "未出现", hit)

    # L30 只在第 2 页（见 l_tokens 注释：不能用去空白文本做行号匹配）
    tok1, tok2 = l_tokens(pages[0]), l_tokens(pages[1])
    record(g, "L30 行只在第 2 页出现",
           f"第 1 页含 L30 = {'L30' in tok1}；第 2 页含 L30 = {'L30' in tok2}",
           "L30" not in tok1 and "L30" in tok2)

    # 表格跨页：两页都有表格行，且第 2 页从第 1 页末行的下一行延续
    rows_p1 = sorted(int(t[1:]) for t in tok1)
    rows_p2 = sorted(int(t[1:]) for t in tok2)
    record(g, "表格从第 1 页延续到第 2 页",
           f"第 1 页行 L{rows_p1[0]}–L{rows_p1[-1]} 共 {len(rows_p1)} 行；"
           f"第 2 页行 L{rows_p2[0]}–L{rows_p2[-1]} 共 {len(rows_p2)} 行",
           bool(rows_p1) and bool(rows_p2) and rows_p2[0] == rows_p1[-1] + 1)

    # 表头行逐页重复（tblHeader 的效果）
    for i, pn in enumerate(page_norms):
        hits = [h for h in HDR_CELLS if h in pn]
        strong = {"必需材料", "对应处理时限", "依据条款"} <= set(hits)
        record(g, f"表头行文字在第 {i+1} 页重复出现",
               f"命中 {hits}", strong)

    # 供报告用的原始抽取样张
    print("──── fixture-table.pdf 每页开头/结尾摘录 ────")
    for i, t in enumerate(pages):
        compact = re.sub(r"\s+", " ", t).strip()
        print(f"[第 {i+1} 页] 头 120 字: {compact[:120]}")
        print(f"[第 {i+1} 页] 尾 120 字: {compact[-120:]}")


# ───────────────────────── b. fixture-scanned.pdf ─────────────────────────
def image_xobjects(page):
    """返回页面 /Resources /XObject 中 Subtype=/Image 的对象信息列表。"""
    out = []
    try:
        res = page.get("/Resources")
        res = res.get_object() if res is not None else None
        xobjs = res.get("/XObject") if res is not None else None
        xobjs = xobjs.get_object() if xobjs is not None else None
        if xobjs:
            for name in xobjs:
                obj = xobjs[name].get_object()
                if obj.get("/Subtype") == "/Image":
                    out.append({
                        "name": str(name),
                        "width": int(obj.get("/Width", -1)),
                        "height": int(obj.get("/Height", -1)),
                        "filter": str(obj.get("/Filter", "")),
                    })
    except Exception as e:  # 资源结构异常时如实记录
        out.append({"error": repr(e)})
    return out


def check_scanned_pdf():
    g = "fixture-scanned.pdf"
    path = os.path.join(FIX, "fixture-scanned.pdf")
    reader = PdfReader(path)
    n = len(reader.pages)
    record(g, "共 1 页", f"页数 = {n}", n == 1)

    text = reader.pages[0].extract_text() or ""
    stripped = text.strip()
    nows = re.sub(r"\s+", "", text)
    record(g, "可抽取文本 0 字符",
           f"extract_text().strip() 长度 = {len(stripped)}；去空白后长度 = {len(nows)}",
           len(stripped) == 0 and len(nows) == 0)

    imgs = image_xobjects(reader.pages[0])
    n_img = len([x for x in imgs if "error" not in x])
    record(g, "含 1 张图片（/Resources /XObject 子类型 /Image）",
           f"图片 XObject 数 = {n_img}；详情 = {imgs}", n_img == 1)


# ───────────────────────── c. fixture-messy.txt ───────────────────────────
def check_messy_txt():
    g = "fixture-messy.txt"
    path = os.path.join(FIX, "fixture-messy.txt")
    with open(path, "rb") as fh:
        raw = fh.read()

    bom = raw[:3] == b"\xef\xbb\xbf"
    record(g, "以 UTF-8 BOM 开头",
           f"前 3 字节 = {raw[:3].hex()}", bom)

    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    record(g, "含 \\r\\n 换行", f"\\r\\n 出现 {crlf} 次；孤立 \\n 出现 {lone_lf} 次", crlf > 0)

    body = raw.decode("utf-8-sig")
    for s in ["ＨＲＣ６０", "ＨＶ３００", "３个工作日", "２０２６-１０-２１"]:
        record(g, f"全角串「{s}」存在", "存在" if s in body else "不存在", s in body)

    split_mo = re.search(r"A-X-[\r\n]+13", body)
    sep = repr(split_mo.group(0)[4:-2]) if split_mo else "无"
    record(g, "条款编号被换行切断（「A-X-」与「13」之间有换行）",
           f"切断分隔符 = {sep}", bool(split_mo))
    # 说明句「重组为 A-X-13 而不是两条」中会出现一次连续 A-X-13，属预期；
    # 数据行本身必须全部被切断，连续出现次数应为 1
    cont_data = re.findall(r"A-X-13(?! 而不是)", body)
    record(g, "（对照）除说明句外无连续的「A-X-13」数据行",
           f"连续出现次数 = {body.count('A-X-13')}（应为 1，即说明句）；"
           f"非说明句连续出现 = {len(cont_data)}",
           body.count("A-X-13") == 1 and len(cont_data) == 0)

    # PROVENANCE 附带声明：横幅位于 BOM 之后
    first_line = body.split("\r\n", 1)[0]
    record(g, "PROVENANCE：来源横幅位于 BOM 之后（首行）",
           f"首行 = {first_line[:40]}…", "来源标注" in first_line or "本地模型" in first_line)


# ───────────────────────── d. DOCX 核心属性 ───────────────────────────────
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}
# OPC 规范里 comments 对应 dc:description
DOCX_PROPS = [
    ("author", "dc:creator"),
    ("last_modified_by", "cp:lastModifiedBy"),
    ("comments", "dc:description"),
    ("category", "cp:category"),
]


def docx_core_props(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("docProps/core.xml").decode("utf-8")
    root = ET.fromstring(xml)
    dump = []
    for el in root:
        tag = el.tag.split("}", 1)[-1]
        if el.text and el.text.strip():
            dump.append(f"{tag}={el.text.strip()}")
    props = {}
    for name, q in DOCX_PROPS:
        el = root.find(q, NS)
        props[name] = el.text if el is not None else None
    return props, dump


def check_docx(fname):
    g = fname
    path = os.path.join(FIX, fname)
    props, dump = docx_core_props(path)
    print(f"──── {fname} docProps/core.xml 全部非空属性 ────")
    for line in dump:
        print(f"  {line[:160]}")
    for name in ["author", "last_modified_by", "comments", "category"]:
        v = props[name]
        ok = has_marker(v)
        record(g, f"核心属性 {name} 已写入来源信息", f"{name} = {v!r}", ok)

    # README 第 1 节附带声称：fixture-table.docx 设置了 tblHeader（重复表头）
    if fname == "fixture-table.docx":
        with zipfile.ZipFile(path) as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
        record(g, "README：表格首行设置了 tblHeader",
               f"w:tblHeader 出现 {doc_xml.count('tblHeader')} 次",
               "w:tblHeader" in doc_xml)


# ───────────────────────── e. PDF 文档信息元数据 ──────────────────────────
PDF_KEYS = ["/Author", "/Title", "/Subject", "/Keywords", "/Creator", "/Producer", "/Comments"]


def check_pdf_meta(fname):
    g = fname
    path = os.path.join(FIX, fname)
    meta = PdfReader(path).metadata
    print(f"──── {fname} PDF 文档信息 ────")
    for k in PDF_KEYS:
        v = meta.get(k) if meta else None
        print(f"  {k} = {v!r}")
    for k in ["/Author", "/Keywords", "/Creator", "/Comments"]:
        v = meta.get(k) if meta else None
        record(g, f"PROVENANCE：{k} 已写入来源信息", f"{k} = {v!r}", has_marker(v))
    for k in ["/Title", "/Subject"]:
        v = meta.get(k) if meta else None
        record(g, "PROVENANCE：/Title /Subject 非空（实测为描述性内容，"
                  "不含来源标注，与 PROVENANCE「已写入来源信息」措辞有出入）",
               f"{k} = {v!r}", bool(v))
    producer = (meta.get("/Producer") or "") if meta else ""
    record(g, "PROVENANCE：/Producer 追加 local-model-added",
           f"/Producer = {producer!r}", "local-model-added" in producer)


# ───────────────── 补充：PROVENANCE 清单 sha256 前缀核对 ──────────────────
SHA_PREFIXES = {  # 取自 PROVENANCE.md 清单（前 16 个十六进制字符）
    "README.md": "ef4d0929447fc97c",
    "_make_fixtures.py": "5fed63a0b2a3bf25",
    "fixture-messy.txt": "01633a07fe88f99f",
    "fixture-table.docx": "4858fd00763b71fd",
    "fixture-table.pdf": "4ccf4ba3b94d7978",
    "fixture-scanned.docx": "7c53bc673260d385",
    "fixture-scanned.pdf": "f6a27b4895e546c8",
}


def check_sha256():
    g = "PROVENANCE sha256（补充核对）"
    for fname, prefix in SHA_PREFIXES.items():
        p = os.path.join(FIX, fname)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        record(g, f"{fname} sha256 前 16 位 = {prefix}…", f"实测 = {h[:16]}…", h.startswith(prefix))


def main():
    check_table_pdf()
    check_scanned_pdf()
    check_messy_txt()
    for f in ["fixture-table.docx", "fixture-scanned.docx"]:
        check_docx(f)
    for f in ["fixture-table.pdf", "fixture-scanned.pdf"]:
        check_pdf_meta(f)
    check_sha256()

    print()
    print("=" * 100)
    print("逐项断言结果（声称 vs 实测）")
    print("=" * 100)
    n_fail = 0
    cur = None
    for group, claimed, actual, ok in RESULTS:
        if group != cur:
            cur = group
            print(f"\n【{group}】")
        mark = "PASS" if ok else "FAIL"
        if not ok:
            n_fail += 1
        print(f"  [{mark}] 声称: {claimed}")
        print(f"         实测: {actual}")
    print()
    total = len(RESULTS)
    print(f"合计 {total} 项断言，PASS {total - n_fail}，FAIL {n_fail}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
