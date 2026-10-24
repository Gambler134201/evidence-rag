"""解析器（S1-T04）：Markdown / TXT / 可提取文本 PDF → 带定位的文本块。

fail-loud 原则（对应 examples/format-fixtures/ 的实测考点）：
- 任何一页 PDF 无可抽取文本 → 显式报 no_text_layer，列出页码，不静默跳过；
- 不可解码、损坏文件报 corrupt_file；
- PDF 抽取的页眉/页脚（跨页重复的边缘行）被剔除并记入 furniture，不进正文块；
- 原始 HTML 不执行，仅作为文本处理。

定位契约：每个块带 locator，能追回原文（标题路径/段落号/页码 + 原文字符区间）。
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from ..errors import IngestError

#  Clause 编号被换行切断的重连规则（fixture-messy.txt 考点：A-X-<CR><CR><LF>13）。
#  仅当行首是编号且行尾是 "字母-字母-" 形态时才合并，避免误伤正常换行。
_CLAUSE_SPLIT_RE = re.compile(r"([A-Za-z]{1,6}-[A-Za-z]{1,6}-)[ \t]*\n[ \t\r\n]*(?=\d)")

MARKDOWN_SUFFIXES = {".md", ".markdown"}
TXT_SUFFIXES = {".txt"}
PDF_SUFFIXES = {".pdf"}


@dataclass
class ParsedBlock:
    text: str
    locator: dict


@dataclass
class ParsedDocument:
    fmt: str
    blocks: list[ParsedBlock]
    furniture: list[str] = field(default_factory=list)
    n_pages: int | None = None


def detect_format(filename: str) -> str:
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in TXT_SUFFIXES:
        return "txt"
    if suffix in PDF_SUFFIXES:
        return "pdf"
    raise IngestError(
        "unsupported_type",
        f"不支持的文件类型：{filename or '(无文件名)'}；首期支持 Markdown、TXT、可提取文本 PDF",
        {"filename": filename, "suffix": suffix},
    )


def _txt_blocks(text: str) -> list[ParsedBlock]:
    """TXT：按空行分段，段落号 + 原文字符区间定位。"""
    blocks: list[ParsedBlock] = []
    para_no = 0
    start = 0
    for para in text.split("\n\n"):
        stripped = para.strip()
        if not stripped:
            start += len(para) + 2
            continue
        begin = text.find(stripped, start)
        end = begin + len(stripped)
        para_no += 1
        blocks.append(
            ParsedBlock(
                text=stripped,
                locator={"kind": "txt", "para": para_no, "source_chars": [begin, end]},
            )
        )
        start = end
    return blocks


def _markdown_blocks(text: str) -> list[ParsedBlock]:
    """Markdown：先按标题路径、再按段落；原始 HTML 不执行，仅按文本处理。"""
    blocks: list[ParsedBlock] = []
    title_path: list[str] = []
    para_no = 0
    start = 0
    for para in text.split("\n\n"):
        raw = para.strip()
        start = text.find(raw, start) if raw else start
        if not raw:
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            title_path = title_path[: level - 1] + [title]
            blocks.append(
                ParsedBlock(
                    text=title,
                    locator={
                        "kind": "markdown",
                        "title_path": list(title_path),
                        "role": "heading",
                        "source_chars": [start, start + len(raw)],
                    },
                )
            )
        else:
            para_no += 1
            blocks.append(
                ParsedBlock(
                    text=raw,
                    locator={
                        "kind": "markdown",
                        "title_path": list(title_path),
                        "para": para_no,
                        "source_chars": [start, start + len(raw)],
                    },
                )
            )
        start += len(raw)
    return blocks


def _pdf_blocks(data: bytes, filename: str) -> tuple[list[ParsedBlock], list[str], int]:
    """PDF：pypdf 逐页抽取；跨页重复的边缘行视为页眉/页脚剔除。

    任何一页无可抽取文本都视为整体失败（no_text_layer）——v1 从严，扫描页
    不允许静默进入正文；页眉页脚规则在 S1-T13 的夹具断言中验证。
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 依赖已锁定，仅防御
        raise IngestError("corrupt_file", "服务器缺少 pypdf", {}) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        n_pages = len(reader.pages)
        page_texts = [(p.extract_text() or "") for p in reader.pages]
    except Exception as exc:
        raise IngestError(
            "corrupt_file",
            f"PDF 解析失败（{filename}）：{type(exc).__name__}: {exc}",
            {"filename": filename},
        ) from exc

    empty_pages = [i + 1 for i, t in enumerate(page_texts) if not t.strip()]
    if empty_pages:
        raise IngestError(
            "no_text_layer",
            f"以下页无可抽取文本，疑似扫描件或图片页：{empty_pages}",
            {"filename": filename, "empty_pages": empty_pages, "n_pages": n_pages},
        )

    lines_per_page = [[ln.strip() for ln in t.splitlines() if ln.strip()] for t in page_texts]
    furniture = _repeated_furniture(lines_per_page)

    blocks: list[ParsedBlock] = []
    masked_furniture = {_mask_digits(f) for f in furniture}
    for page_no, page_text in enumerate(page_texts, start=1):
        kept = [
            ln for ln in (l.strip() for l in page_text.splitlines())
            if ln and _mask_digits(ln) not in masked_furniture
        ]
        body = "\n".join(kept)
        begin = page_text.find(body) if body else 0
        blocks.append(
            ParsedBlock(
                text=body,
                locator={
                    "kind": "pdf",
                    "page": page_no,
                    "source_chars": [begin, begin + len(body)],
                },
            )
        )
    return blocks, furniture, n_pages


def _mask_digits(line: str) -> str:
    """页码类边缘行逐页数字不同（第 1 页 vs 第 2 页），按掩码分组比较。"""
    return re.sub(r"\d+", "#", line)


def _repeated_furniture(lines_per_page: list[list[str]]) -> list[str]:
    """版面重复内容识别（页眉/页脚/跨页重复表头）。

    两个判据同时满足才剔除（掩码 = 数字归一，页码逐页不同也可比）：
    1. 出现在超过一半的页面（页眉/页脚/重复表头的特征）；
    2. 单页内至多出现 2 次——占位数据行可能跨页重复同一文本，但一页会出
       现十几次（fixture-table.pdf 的 L13-L30），那是数据不是装饰。
    代价：正文里恰好逐页重复 1～2 次的样板句会被剔除，v1 接受该取舍。
    """
    n_pages = len(lines_per_page)
    if n_pages < 2:
        return []
    page_presence: dict[str, int] = {}
    max_in_page: dict[str, int] = {}
    sample: dict[str, str] = {}
    for lines in lines_per_page:
        counts: dict[str, int] = {}
        for ln in lines:
            masked = _mask_digits(ln)
            if len(masked.strip()) < 3:  # 过短行（纯页码等）不参与统计
                continue
            counts[masked] = counts.get(masked, 0) + 1
            sample.setdefault(masked, ln)
        for masked, c in counts.items():
            page_presence[masked] = page_presence.get(masked, 0) + 1
            max_in_page[masked] = max(max_in_page.get(masked, 0), c)
    return [
        sample[m] for m in page_presence
        if page_presence[m] > n_pages / 2 and page_presence[m] > 1
        and max_in_page[m] <= 2
    ]


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    """统一入口：类型识别 → 解码/解析 → 带定位的文本块。所有失败抛 IngestError。"""
    fmt = detect_format(filename)

    if fmt == "pdf":
        blocks, furniture, n_pages = _pdf_blocks(data, filename)
        return ParsedDocument(fmt, blocks, furniture, n_pages)

    # 文本类：显式编码策略（utf-8 BOM 优先，退回 GBK），失败不猜。
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("gbk")
        except UnicodeDecodeError as exc:
            raise IngestError(
                "corrupt_file", f"无法按 UTF-8/GBK 解码：{filename}", {"filename": filename}
            ) from exc

    # 换行归一（CRLF/CR → LF），否则 CRLF 文件的段落切分会失效；
    # locator 的 source_chars 以归一后的解码文本为参照。
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if fmt == "txt":
        text = _CLAUSE_SPLIT_RE.sub(r"\1", text)
        blocks = _txt_blocks(text)
    else:
        blocks = _markdown_blocks(text)

    if not blocks or all(not b.text.strip() for b in blocks):
        raise IngestError(
            "empty_text", f"文件可解码但无有效文本内容：{filename}", {"filename": filename}
        )
    return ParsedDocument(fmt, blocks)
