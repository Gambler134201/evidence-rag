"""入库服务（S1-T03/T04）：校验 → 哈希 → 去重 → 建版本与构建 → 解析分块 → 落库。

阶段边界（如实记录）：
- 本版为同步服务函数，任务行同步推进（ingestion_jobs 状态机留痕）；租约与
  后台工作进程在 S2-T05 实现，本版不声称有异步任务能力。
- Embedding 未实现（S1-T05）：embed_hook 为可选注入，仅用于"复用构建时不
  重复发起请求"的计数验证；不伪造向量。
- 去重键 = 知识库内同一逻辑文档 + content_hash + 处理指纹（实施方案 §4-4），
  不跨知识库去重。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .chunking import Chunk, chunk_document, validate_chunk_config
from .config import get_settings
from .errors import IngestError
from .models import (
    Chunk as ChunkRow,
    Document,
    DocumentVersion,
    IndexBuild,
    IngestionJob,
    KnowledgeBase,
)
from .parsers import ParsedDocument, parse_document
from .storage import new_storage_key, save_raw

PARSER_VERSION = "v1-2026-10-24"
MAX_PDF_PAGES = 200


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(processing_config: dict) -> str:
    """处理指纹：分块参数 + 规范化策略 + 解析器版本（变更即新构建）。"""
    payload = json.dumps(
        {"config": processing_config, "parser_version": PARSER_VERSION},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _validate(filename: str, data: bytes, max_bytes: int) -> None:
    if not data:
        raise IngestError("empty_file", f"空文件：{filename}")
    if len(data) > max_bytes:
        raise IngestError(
            "oversized",
            f"文件 {len(data)} 字节超出上限 {max_bytes}",
            {"size": len(data), "limit": max_bytes},
        )
    # 类型检查前置：不支持的类型在建任何数据库行之前就拒绝（请求级错误）。
    from .parsers import detect_format

    detect_format(filename)


def find_reusable_build(
    session: Session, document_id: int, content_hash_hex: str, fp: str
) -> IndexBuild | None:
    """同文档 + 同内容哈希 + 同处理指纹的已就绪构建可复用，不重复 Embedding。"""
    stmt = (
        select(IndexBuild)
        .join(DocumentVersion, DocumentVersion.id == IndexBuild.version_id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.content_hash == content_hash_hex,
            IndexBuild.config_fingerprint == fp,
            IndexBuild.status == "ready",
        )
        .order_by(IndexBuild.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def ingest_version(
    session: Session,
    *,
    kb_id: int,
    document_id: int,
    filename: str,
    data: bytes,
    chunk_config: dict | None = None,
    effective_at: datetime | None = None,
    embed_hook: Callable[[list[Chunk]], None] | None = None,
) -> dict:
    """上传一个新版本并同步处理；返回 {version_id, build_id, reused, n_chunks}。

    reused=True 表示命中已就绪构建：不建新版本、不建新构建、不调用 embed_hook。
    失败时：version/build/job 行保留 failed 状态与可读错误（条件：失败可见），
    不产生 chunks，发布指针不动（当前根本不允许发布失败构建）。
    """
    settings = get_settings()
    _validate(filename, data, max_bytes=settings.ingest_max_bytes)

    doc = session.get(Document, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise IngestError("corrupt_file", f"文档不存在或不属于该知识库: {document_id}")
    if session.get(KnowledgeBase, kb_id) is None:
        raise IngestError("corrupt_file", f"知识库不存在: {kb_id}")

    # PDF 页数上限属于工程配置，超限报 oversized，不误报成扫描件。
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        import io

        try:
            n_pages = len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            n_pages = None  # 解析阶段会给出 corrupt_file 的具体原因
        if n_pages is not None and n_pages > MAX_PDF_PAGES:
            raise IngestError(
                "oversized",
                f"PDF 页数 {n_pages} 超出上限 {MAX_PDF_PAGES}",
                {"n_pages": n_pages, "limit": MAX_PDF_PAGES},
            )

    h = content_hash(data)
    cfg = validate_chunk_config(chunk_config)
    fp = fingerprint(cfg)

    reusable = find_reusable_build(session, document_id, h, fp)
    if reusable is not None:
        return {
            "version_id": reusable.version_id,
            "build_id": reusable.id,
            "reused": True,
            "n_chunks": reusable.total_chunks,
        }

    effective_at = effective_at or datetime.now(timezone.utc)
    version_no = (
        session.execute(
            select(DocumentVersion.version_no)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
            .limit(1)
        ).scalar_one_or_none()
        or 0
    ) + 1

    # 存储键在建行前定稿：不可变触发器禁止任何后补更新（含 storage_key）。
    key = new_storage_key("pdf" if filename.lower().endswith(".pdf") else "txt")
    version = DocumentVersion(
        document_id=document_id,
        version_id=f"doc{document_id}-v{version_no}-{h[:12]}",
        version_no=version_no,
        content_hash=h,
        storage_key=key,
        raw_meta={"filename_pattern": filename.rsplit(".", 1)[-1].lower(), "synthetic": True},
        parser_version=PARSER_VERSION,
        status="draft",
        effective_at=effective_at,
    )
    session.add(version)
    session.flush()
    save_raw(key, data)

    build = IndexBuild(
        version_id=version.id,
        config_fingerprint=fp,
        embedding_model=get_settings().embedding_model or "unconfigured",
        embedding_dimension=get_settings().embedding_dimension,
        chunking_config=cfg,
        status="running",
    )
    session.add(build)
    session.flush()

    job = IngestionJob(
        kb_id=kb_id,
        document_id=document_id,
        version_id=version.id,
        build_id=build.id,
        job_type="parse",
        status="running",
        step="parse",
    )
    session.add(job)
    session.flush()

    version.status = "processing"
    try:
        parsed: ParsedDocument = parse_document(filename, data)
    except IngestError as exc:
        job.status = "failed"
        job.error_class = exc.error_class
        job.error_detail = exc.detail
        build.status = "failed"
        build.error_detail = f"{exc.error_class}: {exc.detail}"
        version.status = "failed"
        version.error_detail = build.error_detail
        return {
            "version_id": version.id,
            "build_id": build.id,
            "reused": False,
            "n_chunks": 0,
            "failed": True,
            "error_class": exc.error_class,
            "error_detail": exc.detail,
        }

    job.status = "succeeded"
    job.step = "chunk"

    chunks = chunk_document(parsed, cfg, max_tokens_approx=None)
    for ordinal, chunk in enumerate(chunks):
        session.add(
            ChunkRow(
                index_build_id=build.id,
                version_id=version.id,
                ordinal=ordinal,
                content=chunk.content,
                content_hash=chunk.content_hash,
                locator=chunk.locator,
            )
        )
    build.total_chunks = len(chunks)
    build.status = "ready"
    build.completed_at = datetime.now(timezone.utc)
    version.status = "ready"

    if embed_hook is not None:
        embed_hook(chunks)

    return {
        "version_id": version.id,
        "build_id": build.id,
        "reused": False,
        "n_chunks": len(chunks),
        "failed": False,
    }
