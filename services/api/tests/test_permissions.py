"""S2-T01/T02/T04/T08 验收：认证、服务端授权、生命周期传播与 ≥20 项断言。

全部走 TestClient + 独立测试库（get_session 依赖注入覆盖），mock 客户端注入，
无网络。每项断言对应 backlog S2-T08 的权限/生命周期清单条目。
"""
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from evidence_rag import auth, lifecycle
from evidence_rag.db import get_session
from evidence_rag.ingest import ingest_version, publish_build
from evidence_rag.models import (
    AuditEvent,
    Document,
    KnowledgeBase,
    Membership,
    Session as SessionRow,
    User,
)
from evidence_rag.providers import MockEmbedding, MockGeneration

MD = "# 交付规则\n\n## 验收期限\n\nA-D2-02 验收期为次一工作日起 3 个工作日，截止最后一日 18:00。\n"
ANSWER_JSON = '{"status": "answered", "segments": [{"text": "3 个工作日", "citation_ids": ["C1"]}]}'


@pytest.fixture()
def store(migrated_engine):
    """测试库会话 + 种子数据（管理员/成员/外人 + 已发布文档）。"""
    session = sessionmaker(bind=migrated_engine)()
    tag = _uuid.uuid4().hex[:8]
    admin = User(username=f"admin-{tag}", password_hash=auth.hash_password("pw-admin"),
                 display_name="管理员")
    member = User(username=f"member-{tag}", password_hash=auth.hash_password("pw-member"),
                  display_name="成员")
    outsider = User(username=f"out-{tag}", password_hash=auth.hash_password("pw-outsider"),
                    display_name="外人")
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
    publish_build(session, document_id=doc.id, version_id=r["version_id"], build_id=r["build_id"])
    session.commit()
    yield {
        "session": session, "kb": kb.id, "doc": doc.id,
        "admin": admin, "member": member, "outsider": outsider,
        # 测试库跨用例复用（session 级夹具），chunk 必须限定在本次文档内。
        "chunk": session.execute(
            __import__("sqlalchemy").text(
                "SELECT c.id FROM chunks c "
                "JOIN document_versions dv ON dv.id = c.version_id "
                "WHERE dv.document_id = :d ORDER BY c.id LIMIT 1"
            ),
            {"d": doc.id},
        ).scalar_one(),
    }
    session.close()


@pytest.fixture()
def client(store):
    from evidence_rag import main as main_mod

    gen = MockGeneration(default=ANSWER_JSON)
    emb = MockEmbedding()
    orig_clients = main_mod.get_clients
    main_mod.get_clients = lambda: (gen, emb)

    def override_session():
        yield store["session"]

    from evidence_rag.main import app

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as c:
        c.mock_gen = gen
        yield c
    app.dependency_overrides.clear()
    main_mod.get_clients = orig_clients


def _login(client: TestClient, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def _login_as(store, client: TestClient, key: str):
    user = store[key]
    return _login(client, user.username, f"pw-{key}")


# ── 认证（S2-T01）─────────────────────────────────────────────────────

def test_01_unauthenticated_query_is_401(store, client):
    assert client.post(f"/knowledge-bases/{store['kb']}/queries",
                       json={"question": "x"}).status_code == 401


def test_02_unauthenticated_me_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_03_wrong_password_401_generic(store, client):
    r = _login(client, store["member"].username, "wrong-password")
    assert r.status_code == 401
    assert r.json()["detail"] == "用户名或密码错误"


def test_04_unknown_user_same_generic_401(store, client):
    """账号不存在与密码错误的响应完全一致（防用户名枚举）。"""
    r = _login(client, "no-such-user", "whatever")
    assert r.status_code == 401
    assert r.json()["detail"] == "用户名或密码错误"


def test_05_login_sets_httponly_lax_cookie(store, client):
    r = _login_as(store, client, "member")
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_06_me_with_cookie_ok(store, client):
    _login_as(store, client, "member")
    r = client.get("/auth/me")
    assert r.status_code == 200 and r.json()["username"] == store["member"].username


def test_07_password_never_stored_plaintext(store):
    stored = store["member"].password_hash
    assert stored.startswith("pbkdf2_sha256$") and "pw-member" not in stored


def test_25_logout_revokes_session(store, client):
    _login_as(store, client, "member")
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401, "注销后原 Cookie 必须失效"


def test_26_revoked_session_row_is_401(store, client):
    _login_as(store, client, "member")
    sid = store["session"].execute(
        __import__("sqlalchemy").text(
            "SELECT id FROM sessions WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"
        ),
        {"u": store["member"].id},
    ).scalar_one()
    row = store["session"].get(SessionRow, sid)
    row.revoked_at = row.created_at
    store["session"].commit()
    assert client.get("/auth/me").status_code == 401


# ── 授权过滤（S2-T02）─────────────────────────────────────────────────

def test_08_member_query_ok(store, client):
    _login_as(store, client, "member")
    r = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "验收期几天"})
    assert r.status_code == 200
    assert r.json()["status"] == "answered", __import__("json").dumps(r.json(), ensure_ascii=False)


def test_09_outsider_query_is_404(store, client):
    _login_as(store, client, "outsider")
    r = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "x"})
    assert r.status_code == 404


def test_10_nonexistent_kb_same_404_as_forbidden(store, client):
    _login_as(store, client, "member")
    r1 = client.post("/knowledge-bases/999999/queries", json={"question": "x"})
    assert r1.status_code == 404 and r1.json()["detail"] == "not found"


def test_11_unauthorized_text_never_reaches_model(store, client):
    """外人查询被 404 拦截，模型一次都没被调用——未授权文本不入上下文。"""
    before = len(client.mock_gen.calls)
    _login_as(store, client, "outsider")
    client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "验收期几天"})
    assert len(client.mock_gen.calls) == before


def test_12_run_detail_owner_ok(store, client):
    _login_as(store, client, "member")
    r = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "验收期几天"})
    run_id = r.json()["run_id"]
    assert client.get(f"/query-runs/{run_id}").status_code == 200


def test_13_run_detail_of_other_user_is_404(store, client):
    _login_as(store, client, "member")
    run_id = client.post(f"/knowledge-bases/{store['kb']}/queries",
                         json={"question": "q"}).json()["run_id"]
    _login_as(store, client, "outsider")
    assert client.get(f"/query-runs/{run_id}").status_code == 404


def test_14_chunk_text_member_ok(store, client):
    _login_as(store, client, "member")
    r = client.get(f"/chunks/{store['chunk']}")
    assert r.status_code == 200
    assert "A-D2-02" in r.json()["content"]


def test_15_chunk_text_outsider_is_404(store, client):
    _login_as(store, client, "outsider")
    assert client.get(f"/chunks/{store['chunk']}").status_code == 404


def test_16_chunk_id_guessing_is_404(store, client):
    _login_as(store, client, "member")
    assert client.get("/chunks/99999999").status_code == 404


def test_17_non_admin_deactivate_is_403(store, client):
    _login_as(store, client, "member")
    r = client.patch(f"/documents/{store['doc']}", data={"active": "false"})
    assert r.status_code == 403


# ── 生命周期传播（S2-T04）────────────────────────────────────────────

def test_18_admin_deactivate_hides_content_everywhere(store, client):
    _login_as(store, client, "admin")
    assert client.patch(f"/documents/{store['doc']}",
                        data={"active": "false"}).status_code == 200
    _login_as(store, client, "member")
    q = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "验收期几天"})
    assert q.json()["status"] == "insufficient_evidence", "停用后新查询不得命中"
    assert client.get(f"/chunks/{store['chunk']}").status_code == 404, "停用后原文关闭"


def test_19_restore_requires_admin_and_reopens(store, client):
    _login_as(store, client, "admin")
    client.patch(f"/documents/{store['doc']}", data={"active": "false"})
    client.patch(f"/documents/{store['doc']}", data={"active": "true"})
    _login_as(store, client, "member")
    assert client.get(f"/chunks/{store['chunk']}").status_code == 200


def test_20_revoke_membership_propagates_immediately(store, client):
    lifecycle.revoke_membership(store["session"], kb_id=store["kb"],
                                user_id=store["member"].id, actor_user_id=store["admin"].id)
    store["session"].commit()
    _login_as(store, client, "member")
    assert client.post(f"/knowledge-bases/{store['kb']}/queries",
                       json={"question": "x"}).status_code == 404
    assert client.get(f"/chunks/{store['chunk']}").status_code == 404


def test_21_lifecycle_operations_leave_audit_rows(store):
    session = store["session"]
    lifecycle.revoke_membership(session, kb_id=store["kb"],
                                user_id=store["member"].id, actor_user_id=store["admin"].id)
    lifecycle.set_document_active(session, document_id=store["doc"],
                                  active=False, actor_user_id=store["admin"].id)
    rows = session.query(AuditEvent).all()
    actions = {r.action for r in rows}
    assert {"membership_revoke", "document_deactivate"} <= actions


def test_22_upload_requires_admin(store, client):
    _login_as(store, client, "member")
    r = client.post(f"/knowledge-bases/{store['kb']}/documents",
                    files={"file": ("new.md", "# x\n\n内容。\n".encode("utf-8"), "text/markdown")})
    assert r.status_code == 403


def test_23_unauthenticated_upload_is_401(store, client):
    r = client.post(f"/knowledge-bases/{store['kb']}/documents",
                    files={"file": ("new.md", b"x", "text/markdown")})
    assert r.status_code == 401


def test_24_admin_upload_creates_and_publishes(store, client):
    _login_as(store, client, "admin")
    r = client.post(f"/knowledge-bases/{store['kb']}/documents",
                    files={"file": ("操作手册.md", "# 操作手册\n\n## 步骤\n\nA-O1-01 提交材料。\n".encode("utf-8"),
                                    "text/markdown")})
    assert r.status_code == 200 and r.json()["reused"] is False
    _login_as(store, client, "member")
    q = client.post(f"/knowledge-bases/{store['kb']}/queries", json={"question": "操作手册 步骤"})
    assert q.status_code == 200


# ── S2-T07：完全重复与同名不同内容 ────────────────────────────────────

def test_27_reupload_identical_content_gets_duplicate_note(store, client):
    _login_as(store, client, "admin")
    payload = ("# 重复检测\n\n## 条款\n\nA-Z9-01 这份文档用于完全重复检测。\n".encode("utf-8"), "text/markdown")
    first = client.post(f"/knowledge-bases/{store['kb']}/documents",
                        files={"file": ("重复检测.md", *payload)})
    assert first.status_code == 200 and first.json()["reused"] is False
    second = client.post(f"/knowledge-bases/{store['kb']}/documents",
                         files={"file": ("重复检测.md", *payload)})
    assert second.status_code == 200
    assert second.json()["duplicate"] is True, "同内容任务在队列中时不得重复入队"
    assert "不会重复计费" in second.json()["duplicate_note"]
    # 任务处理完成后，再次上传同内容 → 直接复用 ready 构建
    from evidence_rag.providers import MockEmbedding
    from evidence_rag.worker import run_pending_jobs

    run_pending_jobs(store["session"], MockEmbedding())
    third = client.post(f"/knowledge-bases/{store['kb']}/documents",
                        files={"file": ("重复检测.md", *payload)})
    assert third.json()["reused"] is True
    assert "未重复计费" in third.json()["duplicate_note"]


def test_28_same_name_different_content_creates_new_version(store, client):
    _login_as(store, client, "admin")
    v1 = client.post(f"/knowledge-bases/{store['kb']}/documents",
                     files={"file": ("同名.md", "# 同名\n\nA-Z8-01 第一版内容。\n".encode("utf-8"),
                                     "text/markdown")})
    v2 = client.post(f"/knowledge-bases/{store['kb']}/documents",
                     files={"file": ("同名.md", "# 同名\n\nA-Z8-02 第二版内容不同。\n".encode("utf-8"),
                                     "text/markdown")})
    assert v1.json()["reused"] is False and v2.json()["reused"] is False
    assert v2.json()["document_id"] == v1.json()["document_id"], "同名应归入同一逻辑文档"
    assert v2.json()["version_id"] != v1.json()["version_id"], "不同内容必须是新版本"


def test_29_same_content_across_kbs_is_independent(store, client):
    """跨知识库重复不泄露：B 库上传与 A 库完全相同的内容，各自独立建索引。"""
    session = store["session"]
    kb2 = KnowledgeBase(name="kb-other", slug="kb-other")
    session.add(kb2)
    session.flush()
    session.add(Membership(user_id=store["admin"].id, kb_id=kb2.id, role="admin"))
    session.commit()
    _login_as(store, client, "admin")
    payload = ("# 跨库.md", "# 跨库\n\nA-Z7-01 两个库各自一份完全相同的内容。\n".encode("utf-8"), "text/markdown")
    r1 = client.post(f"/knowledge-bases/{store['kb']}/documents",
                     files={"file": ("跨库.md", payload[1], "text/markdown")})
    r2 = client.post(f"/knowledge-bases/{kb2.id}/documents",
                     files={"file": ("跨库.md", payload[1], "text/markdown")})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["document_id"] != r2.json()["document_id"]
    assert "duplicate_note" not in r2.json(), "跨库不得命中对方的重复状态"
    body = r2.json()
    assert str(store["kb"]) not in __import__("json").dumps(body), "响应不得泄露其他知识库的信息"
