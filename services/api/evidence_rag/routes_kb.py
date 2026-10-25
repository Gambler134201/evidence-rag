"""知识库管理页面接口（S2-T06）：列表、详情、任务状态、发布/停用/重试。

全部经过 lifecycle 的授权过滤（S2-T02）：成员可见、admin 可变、401/403/404
口径一致。失败原因输出为可读中文（backlog S2-T06 条件 2），不是错误码裸奔。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, lifecycle
from .db import get_session
from .ingest import publish_build
from .models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexBuild,
    IngestionJob,
    KnowledgeBase,
    Membership,
    QueryRun,
    QueryRunEvidence,
)
from .worker import enqueue_ingest

router = APIRouter()


@router.get("/knowledge-bases", tags=["kb"])
def list_kbs(session: Session = Depends(get_session), user=Depends(auth.get_current_user)) -> list[dict]:
    kbs = session.execute(
        select(KnowledgeBase)
        .join(Membership, Membership.kb_id == KnowledgeBase.id)
        .where(Membership.user_id == user.id)
        .order_by(KnowledgeBase.id)
    ).scalars().all()
    return [{"id": kb.id, "name": kb.name, "slug": kb.slug} for kb in kbs]


def _latest_job(session: Session, document_id: int) -> IngestionJob | None:
    return session.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.id.desc()).limit(1)
    ).scalar_one_or_none()


def _job_brief(job: IngestionJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "job_id": job.id, "status": job.status, "step": job.step,
        "attempt": job.attempt, "error_class": job.error_class,
        "error_detail": job.error_detail,
    }


@router.get("/knowledge-bases/{kb_id}/documents", tags=["kb"])
def list_documents(kb_id: int, session: Session = Depends(get_session),
                   user=Depends(auth.get_current_user)) -> list[dict]:
    lifecycle.require_kb_member(session, user.id, kb_id)
    docs = session.execute(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.id)
    ).scalars().all()
    out = []
    for doc in docs:
        active_version = session.get(DocumentVersion, doc.active_version_id) \
            if doc.active_version_id else None
        active_build = session.get(IndexBuild, doc.active_index_build_id) \
            if doc.active_index_build_id else None
        job = _latest_job(session, doc.id)
        # ready 且不是当前版本的构建 → 页面可显式发布
        publishable = session.execute(
            select(IndexBuild.version_id).where(
                IndexBuild.version_id.in_(
                    select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id)),
                IndexBuild.status == "ready",
                IndexBuild.version_id != doc.active_version_id,
            ).distinct()
        ).scalars().all()
        out.append({
            "document_id": doc.id,
            "title": doc.title,
            "deactivated": doc.deactivated_at is not None,
            "active_version_id": doc.active_version_id,
            "active_version": active_version.version_id if active_version else None,
            "active_build_status": active_build.status if active_build else None,
            "total_chunks": active_build.total_chunks if active_build else None,
            "publishable_version_ids": sorted(publishable),
            "latest_job": _job_brief(job),
        })
    return out


@router.post("/knowledge-bases/{kb_id}/documents", tags=["admin"])
def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    auto_publish: bool = Form(True),
    session: Session = Depends(get_session),
    user=Depends(auth.get_current_user),
) -> dict:
    """上传新版本并入队。auto_publish=True 时 worker 处理完成后自动发布；
    前端管理页可传 False 走"上传 → 确认 → 显式发布"的分步流程（原规划 §5）。"""
    lifecycle.require_kb_admin(session, user.id, kb_id)
    data = file.file.read()
    filename = file.filename or "upload.txt"
    title = filename.rsplit(".", 1)[0]
    doc = session.execute(
        select(Document).where(Document.kb_id == kb_id, Document.title == title)
    ).scalar_one_or_none()
    if doc is None:
        doc = Document(kb_id=kb_id, title=title)
        session.add(doc)
        session.flush()
    result = enqueue_ingest(session, kb_id=kb_id, document_id=doc.id,
                            filename=filename, data=data, auto_publish=auto_publish)
    if result.get("reused"):
        result["duplicate_note"] = "内容与现有构建完全一致，已复用索引，未重复计费"
    elif result.get("duplicate"):
        result["duplicate_note"] = "相同内容的任务已在队列中，不会重复计费或建索引"
    session.commit()
    return {"document_id": doc.id, **result}


@router.get("/documents/{document_id}", tags=["kb"])
def document_detail(document_id: int, session: Session = Depends(get_session),
                    user=Depends(auth.get_current_user)) -> dict:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    lifecycle.require_kb_member(session, user.id, doc.kb_id)
    versions = session.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_no)
    ).scalars().all()
    active_build = session.get(IndexBuild, doc.active_index_build_id) \
        if doc.active_index_build_id else None
    chunks = session.execute(
        select(Chunk).where(Chunk.index_build_id == doc.active_index_build_id)
        .order_by(Chunk.ordinal)
    ).scalars().all() if active_build else []
    jobs = session.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.id.desc()).limit(10)
    ).scalars().all()
    return {
        "document_id": doc.id, "kb_id": doc.kb_id, "title": doc.title,
        "deactivated": doc.deactivated_at is not None,
        "active_version_id": doc.active_version_id,
        "active_build_status": active_build.status if active_build else None,
        "versions": [{
            "version_pk": v.id,
            "version_id": v.version_id, "version_no": v.version_no,
            "status": v.status, "effective_at": v.effective_at.isoformat(),
            "is_active": v.id == doc.active_version_id,
            "error_detail": v.error_detail,
        } for v in versions],
        "chunks": [{
            "chunk_id": c.id, "ordinal": c.ordinal,
            "locator": c.locator, "has_vector": c.embedding is not None,
            "preview": c.content[:160],
        } for c in chunks],
        "recent_jobs": [_job_brief(j) for j in jobs],
    }


@router.get("/ingestion-jobs/{job_id}", tags=["kb"])
def job_detail(job_id: int, session: Session = Depends(get_session),
               user=Depends(auth.get_current_user)) -> dict:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    lifecycle.require_kb_member(session, user.id, job.kb_id)
    brief = _job_brief(job)
    assert brief is not None
    brief.update({
        "kb_id": job.kb_id, "document_id": job.document_id,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
    })
    return brief


@router.post("/ingestion-jobs/{job_id}/retry", tags=["admin"])
def retry_job(job_id: int, session: Session = Depends(get_session),
              user=Depends(auth.get_current_user)) -> dict:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    lifecycle.require_kb_admin(session, user.id, job.kb_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="仅失败任务可重试")
    # 手动重试重置尝试次数与退避；错误信息保留到下次执行覆盖。
    job.status = "queued"
    job.attempt = 0
    job.next_retry_at = None
    build = session.get(IndexBuild, job.build_id)
    version = session.get(DocumentVersion, job.version_id)
    if build is not None and build.status == "failed":
        build.status = "pending"
    if version is not None and version.status == "failed":
        version.status = "processing"
    session.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/query-runs", tags=["qa"])
def list_my_runs(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
    user=Depends(auth.get_current_user),
) -> dict:
    """本人运行记录列表（A2 运行记录页）。撤权后对应知识库的记录即从列表消失
    （与 require_run_access 的口径一致）。"""
    from sqlalchemy import exists as sa_exists

    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    member_kb = sa_exists(
        select(Membership.kb_id).where(
            Membership.user_id == user.id, Membership.kb_id == QueryRun.kb_id
        )
    )
    base = select(QueryRun).where(QueryRun.user_id == user.id, member_kb)
    total = session.execute(
        select(__import__("sqlalchemy").func.count()).select_from(base.subquery())
    ).scalar_one()
    runs = session.execute(
        base.order_by(QueryRun.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "total": total,
        "runs": [{
            "run_id": str(r.id), "kb_id": r.kb_id, "question": r.question,
            "status": r.status, "error_class": r.error_class,
            "total_ms": r.total_ms, "created_at": r.created_at.isoformat(),
        } for r in runs],
    }


@router.post("/versions/{version_id}/publish", tags=["admin"])
def publish_version(version_id: int, session: Session = Depends(get_session),
                    user=Depends(auth.get_current_user)) -> dict:
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="not found")
    doc = session.get(Document, version.document_id)
    assert doc is not None
    lifecycle.require_kb_admin(session, user.id, doc.kb_id)
    if version.status != "ready":
        raise HTTPException(status_code=409, detail=f"版本未就绪（当前 {version.status}）")
    build = session.execute(
        select(IndexBuild).where(IndexBuild.version_id == version.id,
                                 IndexBuild.status == "ready")
        .order_by(IndexBuild.id.desc()).limit(1)
    ).scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=409, detail="没有可发布的就绪构建")
    try:
        publish_build(session, document_id=doc.id, version_id=version.id,
                      build_id=build.id, expected_old_version_id=doc.active_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return {"document_id": doc.id, "published_version": version.version_id,
            "active_build_id": build.id}
