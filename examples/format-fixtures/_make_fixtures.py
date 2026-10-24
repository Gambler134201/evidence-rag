# ── 来源标注 ────────────────────────────────────────
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─
# 本脚本由本地模型（DeepSeek Harness 会话助手，非项目作者本人）于 2026-10-21 添加；其生成的夹具文件同样由本地模型生成。
# 详见同目录 PROVENANCE.md。
# ─

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成格式夹具：跨页表格 PDF、脏格式 TXT、无文本层的“扫描样”PDF。
   用途：测试解析器是否会静默丢内容。全部为合成演示资料。"""
import os
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT = os.path.dirname(os.path.abspath(__file__))
EA = "等线"

def run(p, text, size=9, bold=False):
    r = p.add_run(text)
    r.font.size = Pt(size); r.font.bold = bold
    r.font.name = "Calibri"
    r._element.rPr.rFonts.set(qn('w:eastAsia'), EA)
    return r

def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader'); el.set(qn('w:val'), 'true')
    trPr.append(el)

doc = Document()
s = doc.sections[0]
s.page_width, s.page_height = Cm(21.0), Cm(29.7)
s.top_margin = s.bottom_margin = Cm(2.0)

# 页眉页脚：会污染抽取，正是考点
hp = s.header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run(hp, "阶段交付与验收规则（A 库）— 合成演示夹具 — 内部编号 FIXTURE-A-001", size=8)
fp = s.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run(fp, "第 ", size=8)
fld = OxmlElement('w:fldSimple'); fld.set(qn('w:instr'), 'PAGE')
fp._p.append(fld)
run(fp, " 页 / 共 ", size=8)
fld2 = OxmlElement('w:fldSimple'); fld2.set(qn('w:instr'), 'NUMPAGES')
fp._p.append(fld2)
run(fp, " 页", size=8)

p = doc.add_paragraph(); run(p, "A 库附录：验收材料格式夹具（synthetic: true）", size=13, bold=True)
p = doc.add_paragraph()
run(p, "knowledge_base_id: kb-a | document_id: a-format-fixture | version_id: a-format-fixture-v1 | "
       "effective_at: 2026-10-01 | status: current | source: 本项目自行合成 | synthetic: true", size=8)
p = doc.add_paragraph()
run(p, "本夹具用于测试解析与分块，不创设与 A-D2-02 不同的期限。", size=9)

p = doc.add_paragraph(); run(p, "A-X-01 材料分级与提交要求", size=11, bold=True)
p = doc.add_paragraph()
run(p, "接收方退回时，交付方应按下列分级准备材料。分级判定以交付物链接可达性、版本说明完整性与验收项对应关系"
       "三项为准；任一项缺失即判为材料不完整，验收期限不起算。本条不改变 A-D2-02 的 3 个工作日期限。")

# 跨页表格：表头需重复，参数与表头分离是经典失败点
p = doc.add_paragraph(); run(p, "A-X-02 材料分级参数表（表格会跨页，表头应重复）", size=11, bold=True)
rows = [
    ("L1", "交付物链接 + 版本说明 + 验收项清单", "3 个工作日", "A-D2-02"),
    ("L2", "退回整改五项清单（原验收项、问题证据、修复说明、新交付物、未解决项）", "3 个工作日重新起算", "A-R-02"),
    ("L3", "人工协调登记材料（阶段标识、提交日期、适用规则版本、双方意见、证据链接）", "无固定时限", "A-R-03"),
    ("L4", "跨团队引用说明（仅引用有权访问资料）", "不适用", "A-R-04"),
    ("L5", "历史版本回溯申请（需声明访问范围）", "待确认", "A-D1-01"),
    ("L6", "资料泄露报告（转人工，不由助手裁决）", "立即", "A-D2-05"),
    ("L7", "争议证据真实性核验材料", "待确认", "A-R-03"),
    ("L8", "再次提交后的验收意见回执", "3 个工作日", "A-D2-02"),
    ("L9", "提醒发送记录（书面、可核对时间）", "等待 2 个工作日", "A-D2-03"),
    ("L10", "逾期登记工单编号", "不适用", "A-R-03"),
    ("L11", "跨库引用禁止声明", "不适用", "B-D1-03"),
    ("L12", "演示日历口径说明（不含法定节假日）", "不适用", "A-D2-02"),
]
# 故意加长：第一版只有 12 行，整张表落在同一页，测不到跨页考点
rows += [(f"L{i}", "退回整改补充材料（合成占位行，用于制造跨页断点）", "3 个工作日重新起算", "A-R-02")
         for i in range(13, 31)]
t = doc.add_table(rows=1, cols=4); t.style = "Table Grid"
hdr = t.rows[0].cells
for i, h in enumerate(["分级", "必需材料", "对应处理时限", "依据条款"]):
    run(hdr[i].paragraphs[0], h, size=9, bold=True)
repeat_header(t.rows[0])
for r in rows:
    c = t.add_row().cells
    for i, v in enumerate(r):
        run(c[i].paragraphs[0], v, size=9)

p = doc.add_paragraph(); run(p, "A-X-03 跨页条款续写测试", size=11, bold=True)
p = doc.add_paragraph()
run(p, "本条故意把关键结论放在段落末尾，用于测试按固定长度切分时结论是否与前文分离：交付方在再次提交时，"
       "若尚未解决项为空，也必须显式填写「无」，留空不得视为已全部解决——该判定优先于任何默认值推断。")
doc.save(os.path.join(OUT, "fixture-table.docx"))

# 脏 TXT：BOM、全角半角混排、异常换行、条款编号断裂
txt = ("\ufeffA 库格式夹具（TXT 脏格式样）\r\n"
       "document_id: ａ-format-fixture-ｔｘｔ   version_id: a-format-fixture-txt-v1\r\n"
       "synthetic: true   status: current\r\n\r\n"
       "A-X-10 验收材料提交渠道\r\n"
       "交付方应通过站内私聊提交，邮件渠道仅用于\r\n"
       "提醒，不作为完整交付的\r\n"
       "起算依据。\r\n\r\n"
       "A-X-11 全角半角与符号混排\r\n"
       "硬度写 ＨＲＣ６０、ＨＶ３００，也应能匹配 HRC60、HV300；"
       "期限写 ３个工作日、应匹配 3 个工作日；日期 ２０２６-１０-２１ 应匹配 2026-10-21。\r\n\r\n"
       "A-X-12 条款编号断裂样\r\n"
       "A-X-\r\n13 本条编号在原文中被换行切断，解析器应把它识别为 A-X-13 而不是两条。\r\n\r\n"
       "A-X-14 无文本层说明\r\n"
       "同目录 fixture-scanned.pdf 没有文本层，解析器必须显式报错并记录，不得静默跳过。\r\n")
open(os.path.join(OUT, "fixture-messy.txt"), "w", encoding="utf-8-sig", newline="").write(txt)

# 无文本层的“扫描样”PDF：把中文渲染成图片再放进 docx
try:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 34)
    lines = ["扫描样夹具（无文本层）",
             "document_id: a-format-fixture-scanned | synthetic: true",
             "A-X-20 本页面只有图像，没有可抽取文本层。",
             "解析器必须报告“该页无可抽取文本”，",
             "并记录为失败页，不得静默跳过。",
             "若走 OCR，需单独标注 OCR 置信度与人工复核要求。"]
    y = 60
    for ln in lines:
        d.text((60, y), ln, font=f, fill=(35, 35, 35)); y += 120
    png = os.path.join(OUT, "_scanned_page.png")
    img.save(png)
    d2 = Document()
    for sec in d2.sections:
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Cm(1.5)
    pp = d2.add_paragraph(); pp.add_run().add_picture(png, width=Cm(18.0))
    d2.save(os.path.join(OUT, "fixture-scanned.docx"))
    print("scanned docx ok")
except Exception as e:
    print("scanned skipped:", e)

print("docx written to", OUT)
