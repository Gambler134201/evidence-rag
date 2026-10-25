"""S2-T06 验收：管理页面接口——列表、详情、任务可读、发布/重试与授权过滤。"""
import json as _json
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from evidence_rag import lifecycle
from evidence_rag.auth import SESSION_COOKIE, create_session
from evidence_rag.db import get_session
from evidence_rag.ingest import ingest_version, publish_build
from evidence_rag.models import (Chunk, Document, DocumentVersion, IndexBuild,
                                 KnowledgeBase, Membership, User)
from evidence_rag.providers import MockEmbedding, MockGeneration
from evidence_rag.worker import enqueue_ingest, run_pending_jobs

MD = ("# 交付规则\n\n## 验收期限\n\nA-D2-02 验收期为次一工作日起 3 个工作日，"
      "截止最后一日 18:00。\n")


@pytest.fixture()
def store(migrated_engine):
    session = sessionmaker(bind=migrated_engine)()
    tag = _uuid.uuid4().hex[:8]
    admin = User(username=f"admin-{tag}", password_hash="x", display_name="管理员")
    member = User(username=f"member-{tag}", password_hash="x", display_name="成员")
    outsider = User(username=f"out-{tag}", password_hash="x", display_name="外人")
    session.add_all([admin, member, outsider])
    session.flush()
    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    session.add(kb)
    session.flush()
    session.add_all([
        Membership(user_id=admin.id, kb_id=kb.id, role="admin"),
        Membership(user_id=member.id, kb_id=kb.id, role="reader"),
    ])
    doc = Document(kb_id=kb.id, title="交付规则")
    session.add(doc)
    session.flush()
    r = ingest_version(session, kb_id=kb.id, document_id=doc.id, filename="交付规则.md",
                       data=MD.encode("utf-8"), embedder=MockEmbedding())
    publish_build(session, document_id=doc.id, version_id=r["version_id"],
                  build_id=r["build_id"])
    session.commit()
    yield {"session": session, "kb": kb.id, "doc": doc.id,
           "admin": admin, "member": member, "outsider": outsider}
    session.close()


@pytest.fixture()
def client(store, monkeypatch):
    import copy

    from evidence_rag import main as main_mod
    from evidence_rag.config import get_settings as real_get_settings
    from evidence_rag.main import app

    orig = main_mod.get_clients
    fake_settings = copy.deepcopy(real_get_settings())
    fake_settings.retrieval_refuse_score = None
    fake_settings.retrieval_warn_score = None
    monkeypatch.setattr(main_mod, "get_settings", lambda: fake_settings)
    main_mod.get_clients = lambda: (
        MockGeneration(default='{"status":"answered","segments":'
                               '[{"text":"3 个工作日","citation_ids":["C1"]}]}'),
        MockEmbedding(),
    )

    def override_session():
        yield store["session"]

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    main_mod.get_clients = orig


def _as(store, client, key: str):
    """为指定用户直接种会话 Cookie（聚焦页面接口授权，不重复登录流程测试）。"""
    row = create_session(store["session"], store[key].id)
    store["session"].commit()
    client.cookies.set(SESSION_COOKIE, str(row.id))


def _numeric_version_id(store, doc_id: int, version_no: int) -> int:
    return store["session"].execute(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == doc_id,
            DocumentVersion.version_no == version_no)
    ).scalar_one()


def test_list_kbs_shows_only_member_kbs(store, client):
    _as(store, client, "member")
    r = client.get("/knowledge-bases")
    assert r.status_code == 200
    assert [k["id"] for k in r.json()] == [store["kb"]]
    _as(store, client, "outsider")
    assert client.get("/knowledge-bases").json() == [], "外人的列表必须为空"


def test_document_list_shows_active_version_and_build(store, client):
    _as(store, client, "member")
    r = client.get(f"/knowledge-bases/{store['kb']}/documents")
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) == 1
    d = docs[0]
    assert d["title"] == "交付规则"
    assert d["active_version"] and "v1" in d["active_version"]
    assert d["active_build_status"] == "ready"
    assert d["total_chunks"] and d["total_chunks"] >= 1
    assert d["deactivated"] is False


def test_document_detail_exposes_versions_and_located_chunks(store, client):
    """backlog S2-T06 条件 3：版本、生效状态与定位（段落/标题路径）可读。"""
    _as(store, client, "member")
    r = client.get(f"/documents/{store['doc']}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["versions"]) == 1 and body["versions"][0]["is_active"] is True
    assert body["versions"][0]["status"] == "ready"
    assert body["chunks"], "详情页必须有解析预览"
    for c in body["chunks"]:
        loc = c["locator"]
        assert loc.get("title_path") or loc.get("page") or loc.get("para") is not None
        assert c["preview"], "解析预览不能为空"


def test_job_detail_readable_error(store, client):
    """backlog S2-T06 条件 2：失败原因可读（中文 + 分类），不是错误码裸奔。"""
    r = enqueue_ingest(store["session"], kb_id=store["kb"], document_id=store["doc"],
                       filename="broken.pdf", data=b"not-a-pdf")
    run_pending_jobs(store["session"], MockEmbedding())
    _as(store, client, "member")
    detail = client.get(f"/ingestion-jobs/{r['job_id']}").json()
    assert detail["status"] == "failed"
    assert detail["error_class"] == "corrupt_file"
    assert "解析失败" in (detail["error_detail"] or ""), "失败原因必须可读"


def test_retry_requeues_failed_job_admin_only(store, client):
    r = enqueue_ingest(store["session"], kb_id=store["kb"], document_id=store["doc"],
                       filename="broken.pdf", data=b"not-a-pdf")
    run_pending_jobs(store["session"], MockEmbedding())
    _as(store, client, "member")
    assert client.post(f"/ingestion-jobs/{r['job_id']}/retry").status_code == 403
    _as(store, client, "admin")
    ok = client.post(f"/ingestion-jobs/{r['job_id']}/retry")
    assert ok.status_code == 200 and ok.json()["status"] == "queued"
    detail = client.get(f"/ingestion-jobs/{r['job_id']}").json()
    assert detail["status"] == "queued" and detail["attempt"] == 0, "手动重试重置尝试次数"


def test_explicit_publish_flow_unpublished_then_published(store, client):
    """分步流程：上传（不自动发布）→ ready 未发布且不可检索 → 显式发布 → 可检索。"""
    _as(store, client, "admin")
    up = client.post(f"/knowledge-bases/{store['kb']}/documents",
                     files={"file": ("增量.md",
                                     "# 增量\n\n## 新条款\n\nA-Z5-01 增量内容。\n".encode("utf-8"),
                                     "text/markdown")},
                     data={"auto_publish": "false"})
    assert up.status_code == 200, up.text
    run_pending_jobs(store["session"], MockEmbedding())
    doc_id = up.json()["document_id"]
    detail = client.get(f"/documents/{doc_id}").json()
    assert len(detail["versions"]) == 1
    v = detail["versions"][0]
    assert v["status"] == "ready" and v["is_active"] is False,         "未发布前版本不得成为当前版本"
    # 未发布 → 其 chunk 不得出现在任何检索证据里（库中其他已发布文档仍可回答）
    new_build_id = store["session"].execute(
        select(IndexBuild.id).where(
            IndexBuild.version_id == _numeric_version_id(store, doc_id, 1))
    ).scalar_one()
    unpublished_chunks = set(store["session"].execute(
        select(Chunk.id).where(Chunk.index_build_id == new_build_id)
    ).scalars().all())
    assert unpublished_chunks
    _as(store, client, "member")
    q = client.post(f"/knowledge-bases/{store['kb']}/queries",
                    json={"question": "A-Z5-01 增量内容"})
    ev_ids = {e["chunk_id"] for e in q.json()["evidence"]}
    assert ev_ids.isdisjoint(unpublished_chunks), "未发布内容不得被检索"
    # 管理员显式发布 → 立即可检索，且证据里出现新发布的 chunk
    _as(store, client, "admin")
    pub = client.post(f"/versions/{_numeric_version_id(store, doc_id, 1)}/publish")
    assert pub.status_code == 200, pub.text
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["versions"][0]["is_active"] is True
    _as(store, client, "member")
    q2 = client.post(f"/knowledge-bases/{store['kb']}/queries",
                     json={"question": "A-Z5-01 增量内容"})
    assert q2.json()["status"] == "answered", "发布后必须立即可检索"
    ev2 = {e["chunk_id"] for e in q2.json()["evidence"]}
    assert ev2 & unpublished_chunks, "发布后新 chunk 应进入证据"


def test_authorization_on_page_apis(store, client):
    """backlog S2-T06 条件 4：页面数据接口全部经过授权过滤。"""
    _as(store, client, "outsider")
    assert client.get(f"/knowledge-bases/{store['kb']}/documents").status_code == 404
    assert client.get(f"/documents/{store['doc']}").status_code == 404
    vid = store["session"].execute(
        select(DocumentVersion.id).where(DocumentVersion.document_id == store["doc"])
    ).scalar_one()
    assert client.post(f"/versions/{vid}/publish").status_code == 404


# ── A2 运行记录页接口 ─────────────────────────────────────────────────

def _ask(store, client, key: str, question: str) -> str:
    _as(store, client, key)
    r = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": question})
    client.last_ask = _json.dumps(r.json(), ensure_ascii=False)
    return r.json()["run_id"]


def test_runs_list_owner_scoped(store, client):
    run_id = _ask(store, client, "member", "验收期几天？")
    _as(store, client, "member")
    r = client.get("/query-runs")
    assert r.status_code == 200
    ids = [x["run_id"] for x in r.json()["runs"]]
    assert run_id in ids and r.json()["total"] >= 1
    # 外人列表为空（本人可见口径）
    _as(store, client, "outsider")
    assert client.get("/query-runs").json()["runs"] == []


def test_runs_list_disappears_after_revoke(store, client):
    """撤权后对应知识库的运行记录从列表消失（与详情口径一致）。"""
    run_id = _ask(store, client, "member", "验收期几天？")
    lifecycle.revoke_membership(store["session"], kb_id=store["kb"],
                                user_id=store["member"].id, actor_user_id=store["admin"].id)
    store["session"].commit()
    _as(store, client, "member")
    ids = [x["run_id"] for x in client.get("/query-runs").json()["runs"]]
    assert run_id not in ids


def test_runs_list_pagination(store, client):
    _ask(store, client, "member", "问题一")
    _ask(store, client, "member", "问题二")
    page = client.get("/query-runs?limit=1&offset=0").json()
    assert len(page["runs"]) == 1 and page["total"] >= 2


def test_run_detail_includes_evidence_trace(store, client):
    """轨迹查看器：详情含引用编号、定位、分数与片段内容预览。"""
    run_id = _ask(store, client, "member", "验收期限是几天？")
    _as(store, client, "member")
    d = client.get(f"/query-runs/{run_id}").json()
    assert d["evidence"], ("轨迹必须包含证据", d, client.last_ask)
    first = d["evidence"][0]
    assert first["evidence_no"] == "C1"
    assert first["content_preview"], "证据内容预览缺失"
    assert "locator" in first and "score" in first
    assert d["retrieval_ms"] is not None and d["total_ms"] is not None
    assert d["config_snapshot"]["retrieval"] in ("vector", "hybrid")
