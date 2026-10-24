"""S1-T02 测试夹具：专用测试库 evidence_rag_test + Alembic 升到 head。

每次测试会话新建/销毁独立数据库，不污染 .env 指向的开发库。
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from evidence_rag.config import get_settings

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "evidence_rag_test"


def db_url(db: str) -> str:
    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/{db}"
    )


def run_upgrade(url: str, revision: str = "head") -> None:
    """对指定连接串执行 Alembic 升级（测试与幂等性验收共用）。"""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, revision)


@pytest.fixture(scope="session")
def test_db_url():
    return db_url(TEST_DB)


@pytest.fixture(scope="session")
def migrated_engine(test_db_url):
    admin = create_engine(db_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    run_upgrade(test_db_url)
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()

    admin = create_engine(db_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture()
def base_ids(migrated_engine):
    """一组最小基线行，返回 (kb_id, doc_id, ver_id, build_id)。每次调用新建，互不冲突。"""
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:8]
    with migrated_engine.begin() as conn:
        kb = conn.execute(
            text("INSERT INTO knowledge_bases (name, slug) VALUES (:n, :s) RETURNING id"),
            {"n": f"kb-{tag}", "s": f"kb-{tag}"},
        ).scalar_one()
        doc = conn.execute(
            text("INSERT INTO documents (kb_id, title) VALUES (:kb, :t) RETURNING id"),
            {"kb": kb, "t": "交付规则"},
        ).scalar_one()
        ver = conn.execute(
            text(
                "INSERT INTO document_versions (document_id, version_id, version_no, "
                "content_hash, storage_key, parser_version, effective_at) "
                "VALUES (:doc, :vid, 1, 'h0', 'k0', 'p0', now()) RETURNING id"
            ),
            {"doc": doc, "vid": f"v-{tag}"},
        ).scalar_one()
        build = conn.execute(
            text(
                "INSERT INTO index_builds (version_id, config_fingerprint, "
                "embedding_model, embedding_dimension) "
                "VALUES (:ver, 'fp', 'bge-m3', 1024) RETURNING id"
            ),
            {"ver": ver},
        ).scalar_one()
    return {"kb": kb, "doc": doc, "ver": ver, "build": build, "tag": tag}
