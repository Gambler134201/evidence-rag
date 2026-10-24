"""S3-T05 验收：关键词检索（BM25）与 RRF 混合检索——实验 B 的组件级测试。"""
import uuid as _uuid

import pytest
from sqlalchemy.orm import sessionmaker

from evidence_rag.ingest import ingest_version, publish_build
from evidence_rag.models import Document, KnowledgeBase
from evidence_rag.providers import MockEmbedding, MockGeneration
from evidence_rag.rag import answer_question
from evidence_rag.retrieval import search_chunks, search_keyword_chunks

MD = ("# 交付规则\n\n## 验收期限\n\nA-D2-02 接收方应从完整交付的次一工作日起 "
      "3 个工作日内给出验收意见，截止最后一日 18:00。\n"
      "## 未回复处理\n\nA-D2-03 验收期满无意见的，交付方发送一次书面提醒。\n")


@pytest.fixture()
def kb_with_doc(migrated_engine):
    session = sessionmaker(bind=migrated_engine)()
    tag = _uuid.uuid4().hex[:8]
    from evidence_rag.models import User

    user = User(username=f"u-{tag}", password_hash="x", display_name="成员")
    session.add(user)
    session.flush()
    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    session.add(kb)
    session.flush()
    doc = Document(kb_id=kb.id, title="交付规则")
    session.add(doc)
    session.flush()
    r = ingest_version(session, kb_id=kb.id, document_id=doc.id, filename="交付规则.md",
                       data=MD.encode("utf-8"), embedder=MockEmbedding())
    publish_build(session, document_id=doc.id, version_id=r["version_id"],
                  build_id=r["build_id"])
    yield {"session": session, "kb": kb.id, "doc": doc.id, "user": user.id}
    session.close()


def test_keyword_search_hits_exact_clause_id(kb_with_doc):
    """BM25 的卖点：条款编号等精确条件直接命中（向量对编号不敏感）。"""
    top = search_keyword_chunks(kb_with_doc["session"], kb_id=kb_with_doc["kb"],
                                query_text="A-D2-02", top_k=5)
    assert top, "精确条款号必须有命中"
    assert "A-D2-02" in top[0].content
    # 小语料下 BM25 绝对分会退化（IDF 可为负），RRF 只依赖相对排名：
    # A-D2-02 的 chunk 必须排在 A-D2-03 的前面。
    if len(top) > 1:
        assert "A-D2-02" in top[0].content and "A-D2-02" not in top[-1].content


def test_keyword_search_respects_allowed_set(kb_with_doc):
    session = kb_with_doc["session"]
    # 入库但未发布的新文档 → 不在有效集合 → 关键词检索不得命中
    r = ingest_version(session, kb_id=kb_with_doc["kb"], document_id=kb_with_doc["doc"],
                       filename="draft.md",
                       data="# 草稿\n\nA-D9-09 未发布草稿的特殊编号内容。\n".encode("utf-8"),
                       embedder=MockEmbedding())
    assert r["reused"] is False
    top = search_keyword_chunks(session, kb_id=kb_with_doc["kb"],
                                query_text="A-D9-09 未发布草稿", top_k=20)
    assert all("A-D9-09" not in c.content for c in top), "未发布内容进入关键词检索"


def test_hybrid_fuses_and_ranks(kb_with_doc):
    top, candidates = search_chunks(
        kb_with_doc["session"], kb_id=kb_with_doc["kb"], query_text="验收期限 A-D2-02",
        embedder=MockEmbedding(), mode="hybrid", top_k=5, candidate_k=20,
    )
    assert top, "混合检索必须有结果"
    assert "A-D2-02" in top[0].content
    assert all(c.score > 0 for c in candidates)
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True), "RRF 融合分必须降序"


def test_rag_hybrid_mode_end_to_end(kb_with_doc):
    ANSWER = '{"status": "answered", "segments": [{"text": "3 个工作日", "citation_ids": ["C1"]}]}'
    resp = answer_question(
        kb_with_doc["session"], kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
        question="验收期限是几天？", generation=MockGeneration(default=ANSWER),
        embedder=MockEmbedding(), retrieval_mode="hybrid",
    )
    assert resp["status"] == "answered"
    run = kb_with_doc["session"].execute(
        __import__("sqlalchemy").text(
            "SELECT config_snapshot->>'retrieval' FROM query_runs ORDER BY created_at DESC LIMIT 1")
    ).scalar_one()
    assert run == "hybrid", "检索模式必须进入运行记录（可复现实验的前提）"


def test_unknown_mode_rejected(kb_with_doc):
    with pytest.raises(ValueError, match="未知检索模式"):
        search_chunks(kb_with_doc["session"], kb_id=kb_with_doc["kb"],
                      query_text="x", embedder=MockEmbedding(), mode="graph")
