"""S1-T02 验收：数据模型约束的数据库层测试（backlog 条件 2/3/4 的 AUTO 落点）。

所有测试直接对 Alembic 迁移后的真实 PostgreSQL 执行——约束必须由数据库本身
强制，而不是只靠 ORM 代码路径"不存在"。
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from conftest import run_upgrade


def test_migration_idempotent(migrated_engine, test_db_url):
    """backlog S1-T02 条件 4：迁移可重复执行，第二次升级为无操作且不报错。"""
    run_upgrade(test_db_url, "head")  # 已在 head，再次执行必须无副作用
    version = migrated_engine.connect().execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    assert version


def test_document_versions_content_immutable(migrated_engine, base_ids):
    """backlog S1-T02 条件 2 前半：已存在版本的正文列 UPDATE 被数据库拒绝。"""
    with pytest.raises(DBAPIError) as excinfo:
        with migrated_engine.begin() as conn:
            conn.execute(
                text("UPDATE document_versions SET content_hash='tampered' WHERE id=:i"),
                {"i": base_ids["ver"]},
            )
    assert "immutable" in str(excinfo.value.orig)


def test_document_versions_status_transition_allowed(migrated_engine, base_ids):
    """状态列必须放行：draft → ready 流转是任务机的前提。"""
    with migrated_engine.begin() as conn:
        conn.execute(
            text("UPDATE document_versions SET status='ready' WHERE id=:i"),
            {"i": base_ids["ver"]},
        )
        status = conn.execute(
            text("SELECT status FROM document_versions WHERE id=:i"),
            {"i": base_ids["ver"]},
        ).scalar_one()
    assert status == "ready"


def test_document_versions_delete_blocked(migrated_engine, base_ids):
    """正文版本不可删除：历史引用永远有可指向的原文。"""
    with pytest.raises(DBAPIError) as excinfo:
        with migrated_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM document_versions WHERE id=:i"), {"i": base_ids["ver"]}
            )
    assert "immutable" in str(excinfo.value.orig)


def test_chunk_must_match_build_version(migrated_engine, base_ids):
    """backlog S1-T02 条件 3 前半：chunk 的版本必须与其构建的版本一致。"""
    tag = uuid.uuid4().hex[:8]
    with pytest.raises(IntegrityError):
        with migrated_engine.begin() as conn:
            ver_b = conn.execute(
                text(
                    "INSERT INTO document_versions (document_id, version_id, version_no, "
                    "content_hash, storage_key, parser_version, effective_at) "
                    "VALUES (:doc, :vid, 2, 'h1', 'k1', 'p0', now()) RETURNING id"
                ),
                {"doc": base_ids["doc"], "vid": f"v-{tag}-b"},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO chunks (index_build_id, version_id, ordinal, content, "
                    "content_hash, locator) VALUES (:b, :v, 0, 'c', 'h', :loc)"
                ),
                {"b": base_ids["build"], "v": ver_b, "loc": '{"page": 1}'},
            )


def test_chunk_insert_ok_when_version_matches(migrated_engine, base_ids):
    with migrated_engine.begin() as conn:
        chunk = conn.execute(
            text(
                "INSERT INTO chunks (index_build_id, version_id, ordinal, content, "
                "content_hash, locator) VALUES (:b, :v, 0, 'c', 'h', :loc) RETURNING id"
            ),
            {"b": base_ids["build"], "v": base_ids["ver"], "loc": '{"page": 1}'},
        ).scalar_one()
    assert chunk


def test_publish_pointer_must_pair_with_own_build(migrated_engine, base_ids):
    """backlog S1-T02 条件 3 后半：发布指针指向别的版本的构建 → 拒绝。"""
    tag = uuid.uuid4().hex[:8]
    with migrated_engine.begin() as conn:
        ver_b = conn.execute(
            text(
                "INSERT INTO document_versions (document_id, version_id, version_no, "
                "content_hash, storage_key, parser_version, effective_at) "
                "VALUES (:doc, :vid, 2, 'h2', 'k2', 'p0', now()) RETURNING id"
            ),
            {"doc": base_ids["doc"], "vid": f"v-{tag}-b"},
        ).scalar_one()
        build_b = conn.execute(
            text(
                "INSERT INTO index_builds (version_id, config_fingerprint, "
                "embedding_model, embedding_dimension) "
                "VALUES (:ver, 'fp2', 'bge-m3', 1024) RETURNING id"
            ),
            {"ver": ver_b},
        ).scalar_one()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "UPDATE documents SET active_version_id=:v, active_index_build_id=:b "
                    "WHERE id=:d"
                ),
                {"v": base_ids["ver"], "b": build_b, "d": base_ids["doc"]},
            )


def test_publish_pointer_atomic_pair_ok(migrated_engine, base_ids):
    """版本与构建归属一致时，发布指针可以设置；半指针被 CHECK 拒绝。"""
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE documents SET active_version_id=:v, active_index_build_id=:b "
                "WHERE id=:d"
            ),
            {"v": base_ids["ver"], "b": base_ids["build"], "d": base_ids["doc"]},
        )
        # 新文档上只设版本不设构建 → 半指针，CHECK 拒绝。
        doc2 = conn.execute(
            text("INSERT INTO documents (kb_id, title) VALUES (:kb, 'd2') RETURNING id"),
            {"kb": base_ids["kb"]},
        ).scalar_one()
        with pytest.raises(IntegrityError):
            conn.execute(
                text("UPDATE documents SET active_version_id=:v WHERE id=:d"),
                {"v": base_ids["ver"], "d": doc2},
            )


def test_no_two_active_jobs_same_key(migrated_engine, base_ids):
    """backlog S2-T05 前置：同一 (version, job_type) 不允许两个活动任务。"""
    key = {"v": base_ids["ver"], "t": "embed"}
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ingestion_jobs (kb_id, document_id, version_id, build_id, job_type) "
                "VALUES (:kb, :d, :v, :b, :t)"
            ),
            {"kb": base_ids["kb"], "d": base_ids["doc"], "b": base_ids["build"], **key},
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO ingestion_jobs (kb_id, document_id, version_id, build_id, job_type) "
                    "VALUES (:kb, :d, :v, :b, :t)"
                ),
                {"kb": base_ids["kb"], "d": base_ids["doc"], "b": base_ids["build"], **key},
            )


def test_job_requeue_allowed_after_terminal_status(migrated_engine, base_ids):
    """终态后的重试可以再建任务（幂等重试的前提）。"""
    key = {"v": base_ids["ver"], "t": "parse"}
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ingestion_jobs (kb_id, document_id, version_id, build_id, job_type) "
                "VALUES (:kb, :d, :v, :b, :t)"
            ),
            {"kb": base_ids["kb"], "d": base_ids["doc"], "b": base_ids["build"], **key},
        )
        conn.execute(
            text(
                "UPDATE ingestion_jobs SET status='failed' WHERE version_id=:v AND job_type=:t"
            ),
            key,
        )
        second = conn.execute(
            text(
                "INSERT INTO ingestion_jobs (kb_id, document_id, version_id, build_id, job_type) "
                "VALUES (:kb, :d, :v, :b, :t) RETURNING id"
            ),
            {"kb": base_ids["kb"], "d": base_ids["doc"], "b": base_ids["build"], **key},
        ).scalar_one()
    assert second


def test_embedding_dimension_locked(migrated_engine, base_ids):
    """约束 5：维度锁定 1024，其他维度连构建都建不出来。"""
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO index_builds (version_id, config_fingerprint, "
                "embedding_model, embedding_dimension) "
                "VALUES (:ver, 'fp3', 'other-model', 512)"
            ),
            {"ver": base_ids["ver"]},
        )


def test_publish_with_stale_expected_pointer_rejected(migrated_engine, base_ids):
    """S2-T03：并发发布场景——预期旧指针与实际不符时拒绝覆盖较新发布。"""
    import uuid as _uuid

    from sqlalchemy.orm import sessionmaker

    from evidence_rag.ingest import publish_build

    tag = _uuid.uuid4().hex[:8]
    pub = sessionmaker(bind=migrated_engine)()
    with migrated_engine.begin() as conn:
        ver_b = conn.execute(
            text(
                "INSERT INTO document_versions (document_id, version_id, version_no, "
                "content_hash, storage_key, parser_version, effective_at, status) "
                "VALUES (:doc, :vid, 2, 'h2', 'k2', 'p0', now(), 'ready') RETURNING id"
            ),
            {"doc": base_ids["doc"], "vid": f"v-{tag}-b"},
        ).scalar_one()
        build_b = conn.execute(
            text(
                "INSERT INTO index_builds (version_id, config_fingerprint, "
                "embedding_model, embedding_dimension, status) "
                "VALUES (:ver, 'fp-b', 'bge-m3', 1024, 'ready') RETURNING id"
            ),
            {"ver": ver_b},
        ).scalar_one()
    pub.execute(text("UPDATE index_builds SET status='ready' WHERE id=:i"),
                {"i": base_ids["build"]})
    pub.execute(text("UPDATE document_versions SET status='ready' WHERE id=:i"),
                {"i": base_ids["ver"]})
    pub.commit()
    # 第一次发布成功（无预期指针 = 首次发布）。
    publish_build(pub, document_id=base_ids["doc"],
                  version_id=base_ids["ver"], build_id=base_ids["build"])
    pub.commit()
    # 并发任务拿着"预期的旧指针 = NULL"来了：实际已是 ver_a → 拒绝。
    with pytest.raises(ValueError, match="并发发布冲突"):
        publish_build(pub, document_id=base_ids["doc"],
                      version_id=ver_b, build_id=build_b,
                      expected_old_version_id=None)
    # 预期指针正确时才放行。
    publish_build(pub, document_id=base_ids["doc"],
                  version_id=ver_b, build_id=build_b,
                  expected_old_version_id=base_ids["ver"])
    pub.rollback()
    pub.close()


def test_failed_build_publish_rejected(migrated_engine, base_ids):
    """失败构建不发布（S2-T03 条件 3 的服务层断言）。"""
    import uuid as _uuid

    from sqlalchemy.orm import sessionmaker

    from evidence_rag.ingest import publish_build

    tag = _uuid.uuid4().hex[:8]
    pub = sessionmaker(bind=migrated_engine)()
    with migrated_engine.begin() as conn:
        build_failed = conn.execute(
            text(
                "INSERT INTO index_builds (version_id, config_fingerprint, "
                "embedding_model, embedding_dimension, status) "
                "VALUES (:ver, 'fp-f', 'bge-m3', 1024, 'failed') RETURNING id"
            ),
            {"ver": base_ids["ver"]},
        ).scalar_one()
    with pytest.raises(ValueError, match="失败构建不发布"):
        publish_build(pub, document_id=base_ids["doc"],
                      version_id=base_ids["ver"], build_id=build_failed)
    pub.rollback()
    pub.close()
