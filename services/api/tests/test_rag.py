"""S1-T05/T06/T07 验收：向量检索、问答契约、引用校验、运行记录（mock 客户端）。"""
import uuid as _uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from evidence_rag.ingest import ingest_version, publish_build
from evidence_rag.models import QueryRun, QueryRunEvidence
from evidence_rag.providers import MockEmbedding, MockGeneration
from evidence_rag.rag import answer_question
from evidence_rag.retrieval import search_similar_chunks

MD_V1 = (
    "# 交付规则\n\n"
    "## 验收期限\n\n"
    "A-D2-02 接收方应从完整交付的次一工作日起 3 个工作日内给出验收意见，截止为最后一日 18:00。\n"
)

MD_V2 = (
    "# 交付规则\n\n"
    "## 验收期限\n\n"
    "A-D3-01 接收方应从完整交付的次一工作日起 2 个工作日内给出验收意见，截止为最后一日 18:00。\n"
)


@pytest.fixture()
def db_session(migrated_engine):
    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def kb_with_doc(db_session):
    tag = _uuid.uuid4().hex[:8]
    from evidence_rag.models import Document, KnowledgeBase, User

    user = User(username=f"u-{tag}", password_hash="test", display_name="本地用户")
    db_session.add(user)
    db_session.flush()
    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    db_session.add(kb)
    db_session.flush()
    doc = Document(kb_id=kb.id, title="交付规则")
    db_session.add(doc)
    db_session.flush()
    return {"kb": kb.id, "doc": doc.id, "user": user.id}


def _ingest_and_publish(session, kb_id, doc_id, data, embedder):
    result = ingest_version(session, kb_id=kb_id, document_id=doc_id,
                            filename="a.md", data=data.encode("utf-8"), embedder=embedder)
    publish_build(session, document_id=doc_id, version_id=result["version_id"],
                  build_id=result["build_id"])
    return result


def test_retrieval_hits_only_published_version(db_session, kb_with_doc):
    """新版本入库但未发布 → 检索只命中当前发布版本（旧引用不混新内容）。"""
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    ingest_version(db_session, kb_id=kb_with_doc["kb"], document_id=kb_with_doc["doc"],
                   filename="a.md", data=MD_V2.encode("utf-8"), embedder=embedder)
    top, _ = search_similar_chunks(db_session, kb_id=kb_with_doc["kb"],
                                   query_text="验收期限 几个工作日", embedder=embedder)
    assert top, "应命中已发布版本"
    assert all("A-D2-02" in c.content for c in top), "不得命中未发布的 v2 草稿内容"


def test_retrieval_empty_after_deactivate(db_session, kb_with_doc):
    from datetime import datetime, timezone

    from evidence_rag.models import Document

    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    doc = db_session.get(Document, kb_with_doc["doc"])
    doc.deactivated_at = datetime.now(timezone.utc)
    top, _ = search_similar_chunks(db_session, kb_id=kb_with_doc["kb"],
                                   query_text="验收期限", embedder=embedder)
    assert top == [], "停用文档必须立即退出检索"


ANSWER_JSON = '{"status": "answered", "segments": [{"text": "3 个工作日", "citation_ids": ["C1"]}]}'
CLARIFY_JSON = '{"status": "needs_clarification", "segments": [], "clarify": ["哪个团队？"]}'
FENCED_JSON = '```json\n' + ANSWER_JSON + '\n```'


def test_qa_answered_with_valid_citation(db_session, kb_with_doc):
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    gen = MockGeneration(default=ANSWER_JSON)
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="验收期限是几天？", generation=gen, embedder=embedder)
    assert resp["status"] == "answered"
    assert resp["segments"][0]["citation_ids"] == ["C1"]
    assert resp["evidence"][0]["document_title"] == "交付规则"
    run = db_session.get(QueryRun, _uuid.UUID(resp["run_id"]))
    assert run.answer_segments == resp["segments"]
    evidence = db_session.execute(
        select(QueryRunEvidence).where(QueryRunEvidence.run_id == run.id)
    ).scalars().all()
    assert evidence and evidence[0].evidence_no == "C1"
    assert run.cost_note is None and run.prompt_tokens is None, "mock 无用量：留空，不填 0"


def test_qa_tolerates_json_fence(db_session, kb_with_doc):
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="验收期限是几天？",
                           generation=MockGeneration(default=FENCED_JSON), embedder=embedder)
    assert resp["status"] == "answered"


def test_qa_fabricated_citation_blocked(db_session, kb_with_doc):
    """编造编号 → 整体拦截为 error，绝不删标记后照发正文。"""
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    bad = '{"status": "answered", "segments": [{"text": "x", "citation_ids": ["C9"]}]}'
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="验收期限？", generation=MockGeneration(default=bad),
                           embedder=embedder)
    assert resp["status"] == "error" and resp["segments"] == []
    run = db_session.get(QueryRun, _uuid.UUID(resp["run_id"]))
    assert run.error_class == "citation_invalid" and run.answer_segments == []


def test_qa_generation_format_error_blocked(db_session, kb_with_doc):
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="验收期限？", generation=MockGeneration(default="不是 JSON"),
                           embedder=embedder)
    assert resp["status"] == "error"
    run = db_session.get(QueryRun, _uuid.UUID(resp["run_id"]))
    assert run.error_class == "generation_format"


def test_qa_insufficient_when_no_evidence(db_session, kb_with_doc):
    """G2 前置防线：零证据必拒答且不产生任何引用。"""
    embedder = MockEmbedding()
    gen = MockGeneration(default=ANSWER_JSON)  # 即使模型想答，也没有证据可引
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="完全不相关的问题？", generation=gen, embedder=embedder)
    assert resp["status"] == "insufficient_evidence"
    assert resp["evidence"] == [] and resp["segments"] == []
    assert gen.calls == [], "零证据时不得调用生成模型"


def test_qa_needs_clarification_passthrough(db_session, kb_with_doc):
    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)
    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="多久不回复能登记人工？",
                           generation=MockGeneration(default=CLARIFY_JSON), embedder=embedder)
    assert resp["status"] == "needs_clarification"
    assert resp["clarify"] == ["哪个团队？"]


def test_qa_knowledge_changed_on_publish_during_generation(db_session, kb_with_doc):
    """生成期间有效集合变化 → 丢弃正文，返回 knowledge_changed。"""
    from sqlalchemy import update

    from evidence_rag.models import Document

    embedder = MockEmbedding()
    _ingest_and_publish(db_session, kb_with_doc["kb"], kb_with_doc["doc"], MD_V1, embedder)

    class MutatingGen(MockGeneration):
        def chat(self, system, user, **kw):
            db_session.execute(
                update(Document)
                .where(Document.id == kb_with_doc["doc"])
                .values(deactivated_at=datetime_now())
            )
            return super().chat(system, user, **kw)

    def datetime_now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    resp = answer_question(db_session, kb_id=kb_with_doc["kb"], user_id=kb_with_doc["user"],
                           question="验收期限是几天？", generation=MutatingGen(default=ANSWER_JSON),
                           embedder=embedder)
    assert resp["status"] == "knowledge_changed"
    assert resp["segments"] == []
