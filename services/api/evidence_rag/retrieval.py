"""检索层（S1-T05）：AllowedActiveChunks 唯一有效集合 + 精确向量排序。

阶段 1 的有效集合定义（实施方案 §4-3）：当前发布版本 + 文档未停用 +
版本已生效；成员关系过滤在 S2-T02 接入授权后补齐（本版按知识库维度过滤，
不声称已完成越权验证）。全部向量/关键词/原文接口必须复用同一 WHERE 条件。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from .providers import EmbeddingClient

ALLOWED_ACTIVE_SQL = """
d.kb_id = :kb_id
AND d.deactivated_at IS NULL
AND d.active_version_id = c.version_id
AND d.active_index_build_id = c.index_build_id
AND dv.effective_at <= now()
"""


@dataclass
class RetrievedChunk:
    chunk_id: int
    version_id: int
    version_label: str
    document_title: str
    locator: dict
    content: str
    score: float  # 余弦相似度，1 - cosine_distance


def search_similar_chunks(
    session: Session,
    *,
    kb_id: int,
    query_text: str,
    embedder: EmbeddingClient,
    top_k: int = 5,
    candidate_k: int = 20,
) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    """返回 (top_k 最终证据, candidate_k 候选)。候选集用于归因（R1/R2 区分）。"""
    if top_k > candidate_k:
        candidate_k = top_k
    vec = embedder.embed([query_text])[0]
    sql = text(f"""
        SELECT c.id, c.version_id, dv.version_id AS version_label, d.title,
               c.locator, c.content,
               1 - (c.embedding <=> CAST(:vec AS vector)) AS score
        FROM chunks c
        JOIN index_builds b ON b.id = c.index_build_id
        JOIN document_versions dv ON dv.id = c.version_id
        JOIN documents d ON d.id = dv.document_id
        WHERE {ALLOWED_ACTIVE_SQL}
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:vec AS vector)
        LIMIT :limit
    """)
    rows = session.execute(
        sql, {"kb_id": kb_id, "vec": vec, "limit": candidate_k}
    ).mappings().all()
    candidates = [
        RetrievedChunk(
            chunk_id=r["id"],
            version_id=r["version_id"],
            version_label=r["version_label"],
            document_title=r["title"],
            locator=r["locator"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
    ]
    return candidates[:top_k], candidates


def capture_active_snapshot(session: Session, kb_id: int) -> list[tuple]:
    """有效集合快照：问答前/后各取一次，不一致即 knowledge_changed。"""
    rows = session.execute(text("""
        SELECT d.id, d.active_version_id, d.active_index_build_id
        FROM documents d
        WHERE d.kb_id = :kb_id AND d.deactivated_at IS NULL
          AND d.active_version_id IS NOT NULL
        ORDER BY d.id
    """), {"kb_id": kb_id}).all()
    return [tuple(r) for r in rows]
