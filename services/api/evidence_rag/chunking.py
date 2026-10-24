"""分块器（S1-T04）：带标题前缀与重叠，超限显式切分，绝不静默截断。

参数是实验变量而非最优值（实施方案 §5）：默认 300～600 中文字符区间内取
500、重叠 50。token 上限说明：bge-m3 单条上限 8192 tokens，本版以字符数
近似控制（中文约 1 token/1.5 字符，max_chars=500 ≈ 330 tokens，余量充足），
精确 tokenizer 校验在选定 tokenizer 后补充——这是如实记录的近似，不是宣称。

规范化策略进入 processing_config（去重指纹的一部分）：NFKC 全角归一 +
空白折叠 + 条款号断行重连（重连在解析层完成，见 parsers._CLAUSE_SPLIT_RE）。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .parsers import ParsedDocument

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])\s*")
DEFAULT_CHUNK_CONFIG = {
    "max_chars": 500,
    "overlap_chars": 50,
    "normalize": "nfkc+ws_collapse",
    "heading_prefix": True,
}


def validate_chunk_config(config: dict | None) -> dict:
    """配置前置校验：入库建行之前执行，非法配置不产生任何数据库痕迹。"""
    cfg = dict(DEFAULT_CHUNK_CONFIG)
    if config:
        cfg.update(config)
    max_chars = int(cfg["max_chars"])
    overlap = int(cfg["overlap_chars"])
    if not 100 <= max_chars <= 2000:
        raise ValueError(f"max_chars 超出安全范围: {max_chars}")
    if not 0 <= overlap < max_chars:
        raise ValueError(f"overlap_chars 非法: {overlap}")
    return cfg


def normalize_text(text: str) -> str:
    """NFKC 全角→半角 + 空白折叠（fixture-messy.txt 的检索命中考点）。"""
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


@dataclass
class Chunk:
    content: str
    locator: dict
    content_hash: str


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """超限块按句子边界切分，块间保留重叠；单句仍超限则按字符硬切。"""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    sentences = [s for s in SENTENCE_SPLIT_RE.split(text) if s] or [text]
    buf = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if buf:
                pieces.append(buf)
                buf = ""
            step = max(1, max_chars - overlap)
            for i in range(0, len(sentence), step):
                piece = sentence[i : i + max_chars]
                if piece:
                    pieces.append(piece)
            continue
        if buf and len(buf) + len(sentence) > max_chars:
            pieces.append(buf)
            buf = (buf[-overlap:] + sentence) if overlap else sentence
        else:
            buf += sentence
    if buf:
        pieces.append(buf)
    return pieces


def chunk_document(
    parsed: ParsedDocument,
    config: dict | None = None,
    max_tokens_approx: int | None = None,
) -> list[Chunk]:
    """合并段落成块：标题前缀进入块内容；定位取首个成员块并记录成员区间。"""
    cfg = validate_chunk_config(config)
    max_chars = int(cfg["max_chars"])
    overlap = int(cfg["overlap_chars"])

    chunks: list[Chunk] = []
    buf_parts: list[str] = []
    buf_locators: list[dict] = []
    heading: str | None = None

    def flush() -> None:
        nonlocal buf_parts, buf_locators
        if not buf_parts:
            return
        body = " ".join(p["text"] for p in buf_parts)
        content = f"[{heading}] {body}" if (heading and cfg["heading_prefix"]) else body
        pieces = _split_long(content, max_chars, overlap)
        for i, piece in enumerate(pieces):
            first_locator = dict(buf_locators[0].locator)
            first_locator["piece"] = f"{i + 1}/{len(pieces)}"
            first_locator["members"] = [p.locator for p in buf_locators]
            chunks.append(Chunk(content=normalize_text(piece), locator=first_locator, content_hash=""))
        buf_parts, buf_locators = [], []

    for block in parsed.blocks:
        if block.locator.get("role") == "heading":
            flush()
            heading = normalize_text(block.text)
            continue
        normalized = normalize_text(block.text)
        if not normalized:
            continue
        buf_parts.append({"text": normalized})
        buf_locators.append(block)
        if sum(len(p["text"]) for p in buf_parts) >= max_chars:
            flush()
    flush()

    for chunk in chunks:
        chunk.content_hash = _hash(chunk.content)
    if max_tokens_approx and any(len(c.content) > max_tokens_approx for c in chunks):
        # 以字符近似 token 的防御线：真超限时显式失败而非静默截断。
        longest = max(len(c.content) for c in chunks)
        raise ValueError(f"chunk 超出近似 token 上限: {longest} chars")
    return chunks
