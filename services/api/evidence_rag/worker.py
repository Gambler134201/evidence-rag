"""入库任务后台进程（S2-T05）：认领、租约、重试、幂等续跑。

架构语义（对应 backlog S2-T05 与实施方案 §3/§5，全部可测试验证）：
- **认领互斥**：`FOR UPDATE SKIP LOCKED` 单条认领，多个工作进程不会拿到同一任务；
- **租约**：认领即写 lease_until；执行中每批 Embedding 后续租（心跳）。进程崩溃
  后租约到期，由 reap_expired 重置回 queued，其他进程可接手；
- **至少一次，不承诺恰好一次**：外部 Embedding 调用无法纳入本地事务，靠幂等
  （断点续跑 + 内容哈希去重）收敛，不宣称零重复费用；
- **重试**：失败按 attempt 退避重排，超过 MAX_ATTEMPTS 才置 failed；
- **幂等续跑**：chunk 行先落库（向量留空），Embedding 按 embedded_until 断点
  分批执行，进度随批提交——中断后从断点继续，不重复已成功的调用。

与同步链路的关系：`ingest_version`（S1）保留给评测脚本与测试；线上上传走
enqueue → worker 异步路径。两者共用 parsers/chunking/storage 组件。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .chunking import chunk_document
from .config import get_settings
from .errors import IngestError
from .log_redact import redact
from .ingest import (
    PARSER_VERSION,
    MAX_PDF_PAGES,
    content_hash,
    fingerprint,
    find_reusable_build,
)
from .models import (
    Chunk as ChunkRow,
    Document,
    DocumentVersion,
    IndexBuild,
    IngestionJob,
)
from .parsers import parse_document
from .storage import new_storage_key, save_raw, storage_path

LEASE_SECONDS = 120
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 30
EMBED_BATCH = 16


def enqueue_ingest(
    session: Session,
    *,
    kb_id: int,
    document_id: int,
    filename: str,
    data: bytes,
    auto_publish: bool = True,
) -> dict:
    """上传入队：创建 draft 版本 + pending 构建 + queued 任务（幂等）。

    - 同文档同哈希已有 queued/running 任务 → 返回该 job_id（duplicate）；
    - 同文档同哈希已有 ready 构建 → 直接复用（reused，不重复 Embedding）；
    - 同名不同内容 = 新版本，正常入队。
    """
    from .ingest import _validate

    _validate(filename, data, get_settings().ingest_max_bytes)
    if filename.lower().endswith(".pdf"):
        import io

        from pypdf import PdfReader

        try:
            n_pages = len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            n_pages = None
        if n_pages is not None and n_pages > MAX_PDF_PAGES:
            raise IngestError("oversized", f"PDF 页数 {n_pages} 超出上限 {MAX_PDF_PAGES}",
                              {"n_pages": n_pages})

    doc = session.get(Document, document_id)
    if doc is None or doc.kb_id != kb_id:
        raise IngestError("corrupt_file", f"文档不存在或不属于该知识库: {document_id}")

    h = content_hash(data)
    fp = fingerprint({})  # worker 使用默认分块配置

    reusable = find_reusable_build(session, document_id, h, fp)
    if reusable is not None:
        return {"job_id": None, "reused": True, "build_id": reusable.id,
                "version_id": reusable.version_id}

    # 已有同内容版本：复用该版本/构建行，只补任务（避免重复 Embedding 计费风险）。
    version = session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id,
               DocumentVersion.content_hash == h)
        .order_by(DocumentVersion.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is not None:
        build = session.execute(
            select(IndexBuild).where(IndexBuild.version_id == version.id,
                                     IndexBuild.config_fingerprint == fp)
            .order_by(IndexBuild.id.desc()).limit(1)
        ).scalar_one_or_none()
        if build is not None:
            active = session.execute(
                select(IngestionJob).where(
                    IngestionJob.version_id == version.id,
                    IngestionJob.build_id == build.id,
                    IngestionJob.status.in_(["queued", "running"]),
                ).order_by(IngestionJob.id.desc()).limit(1)
            ).scalar_one_or_none()
            if active is not None:
                return {"job_id": active.id, "duplicate": True, "reused": False,
                        "version_id": version.id, "build_id": build.id}
            job = _new_job(session, kb_id=kb_id, document_id=document_id,
                           version_id=version.id, build_id=build.id,
                           auto_publish=auto_publish)
            return {"job_id": job.id, "reused": False, "duplicate": False,
                    "version_id": version.id, "build_id": build.id}

    key = new_storage_key("pdf" if filename.lower().endswith(".pdf") else "txt")
    save_raw(key, data)
    version_no = (
        session.execute(
            select(DocumentVersion.version_no)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc()).limit(1)
        ).scalar_one_or_none() or 0
    ) + 1
    # 存储键/内容列建行即定稿：不可变触发器禁止后补更新。
    version = DocumentVersion(
        document_id=document_id,
        version_id=f"doc{document_id}-v{version_no}-{h[:12]}",
        version_no=version_no,
        content_hash=h,
        storage_key=key,
        raw_meta={"filename_pattern": filename.rsplit(".", 1)[-1].lower(), "synthetic": True},
        parser_version=PARSER_VERSION,
        status="draft",
        effective_at=func_now(),
    )
    session.add(version)
    session.flush()
    build = IndexBuild(
        version_id=version.id,
        config_fingerprint=fp,
        embedding_model=get_settings().embedding_model or "unconfigured",
        embedding_dimension=get_settings().embedding_dimension,
        chunking_config={},
        status="pending",
    )
    session.add(build)
    session.flush()
    job = _new_job(session, kb_id=kb_id, document_id=document_id,
                   version_id=version.id, build_id=build.id, auto_publish=auto_publish)
    return {"job_id": job.id, "reused": False, "duplicate": False,
            "version_id": version.id, "build_id": build.id}


def _new_job(session: Session, *, kb_id: int, document_id: int,
             version_id: int, build_id: int, auto_publish: bool) -> IngestionJob:
    job = IngestionJob(
        kb_id=kb_id, document_id=document_id, version_id=version_id,
        build_id=build_id, job_type="parse", status="queued",
        progress={"auto_publish": auto_publish, "embedded_until": 0},
    )
    session.add(job)
    session.flush()
    return job


def func_now():
    """生效时间用数据库时钟（同 ingest 的教训：Python 时钟会被自己的判定滤掉）。"""
    from sqlalchemy import func

    return func.now()


def claim_job(session: Session) -> IngestionJob | None:
    """认领一条 queued 任务（SKIP LOCKED 互斥），置 running 并写租约。"""
    row = session.execute(
        text("""
            UPDATE ingestion_jobs
            SET status = 'running',
                attempt = attempt + 1,
                lease_until = now() + make_interval(secs => :lease),
                updated_at = now()
            WHERE id = (
                SELECT id FROM ingestion_jobs
                WHERE status = 'queued'
                  AND (next_retry_at IS NULL OR next_retry_at <= now())
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id
        """),
        {"lease": LEASE_SECONDS},
    ).scalar_one_or_none()
    session.commit()
    if row is None:
        return None
    return session.get(IngestionJob, row)


def reap_expired(session: Session) -> int:
    """回收租约到期的 running 任务 → 重新排队（崩溃恢复路径）。"""
    res = session.execute(text("""
        UPDATE ingestion_jobs
        SET status = 'queued', lease_until = NULL, updated_at = now()
        WHERE status = 'running' AND lease_until < now()
        RETURNING id
    """))
    ids = [r[0] for r in res.all()]
    session.commit()
    return len(ids)


def run_job(session: Session, job_id: int, embedder) -> str:
    """执行单个任务；返回最终状态（succeeded/failed/queued=待重试）。

    断点续跑：chunk 行先整体落库（向量留空）+ 进度标记一次提交；Embedding 按
    EMBED_BATCH 分批，每批后提交进度并续租。崩溃后重跑只补 remaining。
    """
    job = session.get(IngestionJob, job_id)
    if job is None or job.status != "running":
        return job.status if job else "missing"
    build = session.get(IndexBuild, job.build_id)
    version = session.get(DocumentVersion, job.version_id)
    build.status = "running"
    version.status = "processing"
    session.commit()

    try:
        if not job.progress.get("chunks_written"):
            # 首次执行：解析 → 分块 → chunk 行整体落库（向量留空）。
            # 重试时此块整体跳过（进度标记与 chunk 行同批提交，天然原子）。
            data = storage_path(version.storage_key).read_bytes()
            parsed = parse_document(filename=f"{version.version_id}.{_ext_of(version)}", data=data)
            chunks = chunk_document(parsed, build.chunking_config or {}, max_tokens_approx=None)
            for ordinal, chunk in enumerate(chunks):
                session.add(ChunkRow(
                    index_build_id=build.id, version_id=version.id, ordinal=ordinal,
                    content=chunk.content, content_hash=chunk.content_hash,
                    locator=chunk.locator,
                ))
            job.progress = {**job.progress, "chunks_written": True}
            build.total_chunks = len(chunks)
            session.commit()
    except IngestError as exc:
        return _fail(session, job, build, version, exc.error_class, exc.detail)
    except Exception as exc:  # 分块/读文件等未分类错误也要可见
        return _fail(session, job, build, version, "corrupt_file",
                     f"{type(exc).__name__}: {exc}")

    rows = session.execute(
        select(ChunkRow).where(ChunkRow.index_build_id == build.id)
        .order_by(ChunkRow.ordinal)
    ).scalars().all()
    until = int(job.progress.get("embedded_until", 0))
    try:
        while until < len(rows):
            batch = rows[until : until + EMBED_BATCH]
            vectors = embedder.embed([r.content for r in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("embedding_batch_size_mismatch")
            for row, vec in zip(batch, vectors):
                row.embedding = vec
            until += len(batch)
            # 进度 + 心跳同批提交：崩溃后最多重做一批。
            job.progress = {**job.progress, "embedded_until": until}
            job.step = "embed"
            session.execute(text(
                "UPDATE ingestion_jobs SET lease_until = now() + make_interval(secs => :s) "
                "WHERE id = :i"
            ), {"s": LEASE_SECONDS, "i": job.id})
            session.commit()
    except Exception as exc:
        session.rollback()
        return _retry_or_fail(session, job, build, version,
                              "embedding_error", f"{type(exc).__name__}: {exc}")

    build.status = "ready"
    build.completed_at = datetime.now(timezone.utc)
    version.status = "ready"
    job.status = "succeeded"
    job.step = "done"
    if job.progress.get("auto_publish"):
        from .ingest import publish_build

        doc = session.get(Document, job.document_id)
        publish_build(session, document_id=doc.id, version_id=version.id,
                      build_id=build.id, expected_old_version_id=doc.active_version_id)
    session.commit()
    return "succeeded"


def _fail(session: Session, job, build, version, error_class: str, detail: str) -> str:
    job.status = "failed"
    job.error_class = error_class
    job.error_detail = redact(detail)[:500]
    build.status = "failed"
    build.error_detail = f"{error_class}: {detail}"[:500]
    version.status = "failed"
    version.error_detail = build.error_detail
    session.commit()
    return "failed"


def _retry_or_fail(session: Session, job, build, version, error_class: str, detail: str) -> str:
    if job.attempt >= MAX_ATTEMPTS:
        return _fail(session, job, build, version, error_class, detail)
    job.status = "queued"
    job.error_class = error_class
    job.error_detail = redact(detail)[:500]
    job.next_retry_at = datetime.now(timezone.utc) + timedelta(
        seconds=BACKOFF_SECONDS * job.attempt
    )
    job.step = "retry"
    build.status = "pending"
    version.status = "processing"
    session.commit()
    return "queued"


def _ext_of(version: DocumentVersion) -> str:
    return (version.storage_key.rsplit(".", 1)[-1] or "txt")[:7]


def run_pending_jobs(session: Session, embedder, max_jobs: int = 50) -> list[str]:
    """测试与运维辅助：串行处理全部待办任务（生产用 run_worker_loop）。"""
    done = []
    for _ in range(max_jobs):
        job = claim_job(session)
        if job is None:
            break
        done.append(run_job(session, job.id, embedder))
    return done


def run_worker_loop() -> None:
    """生产入口：`python -m evidence_rag.worker`。真实客户端由开关决定。"""
    from .db import SessionLocal
    from .providers import get_clients

    _, embedder = get_clients()
    session = SessionLocal()
    idle = 0
    while True:
        reap_expired(session)
        job = claim_job(session)
        if job is None:
            idle += 1
            time.sleep(min(5, idle))
            continue
        idle = 0
        try:
            run_job(session, job.id, embedder)
        except Exception as exc:  # noqa: BLE001 — 工作进程不能被单个任务打死
            session.rollback()
            print(f"worker: job {job.id} crashed: {type(exc).__name__}: {exc}")
            _retry_or_fail(session, session.get(IngestionJob, job.id),
                           session.get(IndexBuild, job.build_id),
                           session.get(DocumentVersion, job.version_id),
                           "internal_error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    run_worker_loop()
