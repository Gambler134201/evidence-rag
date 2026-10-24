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


# ── 关键词检索与 RRF 融合（S3-T05，实验 B）────────────────────────────

_ALNUM_RE = None


def _tokenize(text: str) -> list[str]:
    """jieba 搜索模式切词 + 过滤纯标点/符号 token。

    标点（如 "-"）在 BM25 里会产生负 IDF 拖垮整句得分，且本身不是检索词；
    保留字母数字与 CJK。jieba 会把英文统一小写，查询与语料两侧一致。
    """
    global _ALNUM_RE
    if _ALNUM_RE is None:
        import re

        _ALNUM_RE = re.compile(r"[0-9a-z一-鿿]+$")
    import jieba

    return [t for t in jieba.lcut_for_search(text.lower()) if _ALNUM_RE.match(t)]


def _load_allowed_chunks(session: Session, kb_id: int, limit: int) -> list[RetrievedChunk]:
    """有效集合内全部 chunk（小语料内存 BM25 的规模前提）。"""
    rows = session.execute(text(f"""
        SELECT c.id, c.version_id, dv.version_id AS version_label, d.title,
               c.locator, c.content
        FROM chunks c
        JOIN index_builds b ON b.id = c.index_build_id
        JOIN document_versions dv ON dv.id = c.version_id
        JOIN documents d ON d.id = dv.document_id
        WHERE {ALLOWED_ACTIVE_SQL}
        LIMIT :limit
    """), {"kb_id": kb_id, "limit": limit}).mappings().all()
    return [
        RetrievedChunk(
            chunk_id=r["id"], version_id=r["version_id"],
            version_label=r["version_label"], document_title=r["title"],
            locator=r["locator"], content=r["content"], score=0.0,
        ) for r in rows
    ]


def search_keyword_chunks(
    session: Session,
    *,
    kb_id: int,
    query_text: str,
    top_k: int = 5,
    candidate_k: int = 20,
    corpus_limit: int = 5000,
) -> list[RetrievedChunk]:
    """中文关键词检索：jieba 搜索模式切词 + BM25，只在授权有效集合内计算。

    按实施方案 §8：jieba（MIT）+ rank_bm25（Apache-2.0）为小规模、可替换的
    实验基线候选；语料规模超出内存 BM25 代价时再评估外部检索组件。
    """
    if top_k > candidate_k:
        candidate_k = top_k
    import jieba
    from rank_bm25 import BM25Okapi

    pool = _load_allowed_chunks(session, kb_id, corpus_limit)
    if not pool:
        return []
    tokenized = [_tokenize(c.content) for c in pool]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(_tokenize(query_text))
    ranked = sorted(zip(pool, scores), key=lambda pair: pair[1], reverse=True)[:candidate_k]
    return [
        RetrievedChunk(
            chunk_id=c.chunk_id, version_id=c.version_id,
            version_label=c.version_label, document_title=c.document_title,
            locator=c.locator, content=c.content, score=float(s),
        )
        for c, s in ranked
    ]


def search_hybrid_chunks(
    session: Session,
    *,
    kb_id: int,
    query_text: str,
    embedder: EmbeddingClient,
    top_k: int = 5,
    candidate_k: int = 20,
    rrf_k: int = 60,
) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    """实验 B：向量 + 关键词两路召回，RRF 融合（常数 rrf_k=60 为文献默认，
    是实验变量而非最优值；融合只在授权有效集合内）。"""
    if top_k > candidate_k:
        candidate_k = top_k
    vec_top, _ = search_similar_chunks(
        session, kb_id=kb_id, query_text=query_text, embedder=embedder,
        top_k=candidate_k, candidate_k=candidate_k,
    )
    kw_top = search_keyword_chunks(
        session, kb_id=kb_id, query_text=query_text,
        top_k=candidate_k, candidate_k=candidate_k,
    )
    fused: dict[int, dict] = {}
    for ranking in (vec_top, kw_top):
        for rank, chunk in enumerate(ranking, start=1):
            entry = fused.setdefault(chunk.chunk_id, {"chunk": chunk, "score": 0.0})
            entry["score"] += 1.0 / (rrf_k + rank)
    ordered = sorted(fused.values(), key=lambda e: e["score"], reverse=True)[:candidate_k]
    candidates = []
    for entry in ordered:
        chunk = entry["chunk"]
        candidates.append(RetrievedChunk(
            chunk_id=chunk.chunk_id, version_id=chunk.version_id,
            version_label=chunk.version_label, document_title=chunk.document_title,
            locator=chunk.locator, content=chunk.content, score=entry["score"],
        ))
    return candidates[:top_k], candidates


def search_chunks(
    session: Session,
    *,
    kb_id: int,
    query_text: str,
    embedder: EmbeddingClient,
    mode: str = "vector",
    top_k: int = 5,
    candidate_k: int = 20,
) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    """统一入口：mode = vector（实验 A 基线）| hybrid（实验 B，向量+BM25 RRF）。"""
    if mode == "hybrid":
        return search_hybrid_chunks(
            session, kb_id=kb_id, query_text=query_text, embedder=embedder,
            top_k=top_k, candidate_k=candidate_k,
        )
    if mode != "vector":
        raise ValueError(f"未知检索模式: {mode}")
    return search_similar_chunks(
        session, kb_id=kb_id, query_text=query_text, embedder=embedder,
        top_k=top_k, candidate_k=candidate_k,
    )
