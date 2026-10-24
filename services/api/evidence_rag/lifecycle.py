"""生命周期操作与授权判定（S2-T02/T04）。

404/401/403 口径（实施方案 §6）：
- 未登录 401；
- 对象不存在或无权访问一律 404（不区分"不存在"与"不可见"）；
- 已是成员但角色不足（非管理员做管理操作）403——身份可辨识，操作被拒。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, Chunk, Document, KnowledgeBase, Membership, QueryRun


def require_kb_member(session: Session, user_id: int, kb_id: int) -> Membership:
    """成员身份判定；kb 不存在与无权限同样 404。"""
    kb = session.get(KnowledgeBase, kb_id)
    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.kb_id == kb_id,
        )
    ).scalar_one_or_none()
    if kb is None or membership is None:
        raise HTTPException(status_code=404, detail="not found")
    return membership


def require_kb_admin(session: Session, user_id: int, kb_id: int) -> Membership:
    membership = require_kb_member(session, user_id, kb_id)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员角色")
    return membership


def require_chunk_access(session: Session, user_id: int, chunk_id: int) -> Chunk:
    """原文访问：chunk 必须属于"成员可见 + 当前发布 + 未停用 + 已生效"的集合。"""
    from .models import DocumentVersion

    chunk = session.get(Chunk, chunk_id)
    visible = False
    if chunk is not None:
        row = session.execute(
            select(Document.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.id == chunk.version_id,
                Document.kb_id.in_(
                    select(Membership.kb_id).where(Membership.user_id == user_id)
                ),
                Document.deactivated_at.is_(None),
                Document.active_version_id == chunk.version_id,
                Document.active_index_build_id == chunk.index_build_id,
            )
        ).first()
        visible = row is not None
    if not visible:
        raise HTTPException(status_code=404, detail="not found")
    return chunk


def require_run_access(session: Session, user_id: int, run_id) -> QueryRun:
    """运行记录仅本人可见（实施方案 §7：本人可见的运行记录和反馈）。"""
    run = session.get(QueryRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="not found")
    # 撤权后运行记录同样不可见（backlog S2-T02 条件 2/3）。
    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.kb_id == run.kb_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="not found")
    return run


def set_document_active(
    session: Session, *, document_id: int, active: bool, actor_user_id: int | None
) -> None:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    if active and doc.active_version_id is None:
        raise HTTPException(status_code=409, detail="恢复前需要有效构建（当前无发布版本）")
    doc.deactivated_at = None if active else datetime.now(timezone.utc)
    session.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="document_deactivate" if not active else "document_restore",
            object_type="document",
            object_id=str(document_id),
            detail={"active": active},
        )
    )
    session.flush()


def revoke_membership(
    session: Session, *, kb_id: int, user_id: int, actor_user_id: int | None
) -> None:
    membership = session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.kb_id == kb_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(membership)
    session.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="membership_revoke",
            object_type="membership",
            object_id=f"{kb_id}:{user_id}",
            detail={},
        )
    )
    session.flush()
