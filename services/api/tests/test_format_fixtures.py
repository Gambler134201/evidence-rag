"""S1-T13 验收：用真实格式夹具断言解析器 fail-loud、不静默丢内容。

夹具与期望行为定义：examples/format-fixtures/README.md 第 3 节；
实测背景：evals/fixture-check-20261024.md。这些断言即 backlog S1-T13 的
AUTO 验收条件，全部使用仓库内真实夹具文件，不使用简化样本。
"""
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import REPO_ROOT

from evidence_rag.errors import IngestError
from evidence_rag.ingest import ingest_version
from evidence_rag.models import Chunk

FIXTURES = REPO_ROOT / "examples" / "format-fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture()
def db_session(migrated_engine):
    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def base_row(db_session):
    import uuid as _uuid

    from evidence_rag.models import Document, KnowledgeBase

    tag = _uuid.uuid4().hex[:8]
    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    db_session.add(kb)
    db_session.flush()
    doc = Document(kb_id=kb.id, title="夹具")
    db_session.add(doc)
    db_session.flush()
    return {"kb": kb.id, "doc": doc.id}


def _chunks_for(db_session, build_id: int) -> list[str]:
    return db_session.execute(
        select(Chunk.content).where(Chunk.index_build_id == build_id).order_by(Chunk.ordinal)
    ).scalars().all()


def test_scanned_pdf_fails_loud_with_page_list(db_session, base_row, monkeypatch):
    """扫描样夹具必须显式失败并列出失败页，禁止静默跳过或空 chunk 记成功。"""
    import tempfile
    from evidence_rag import storage as storage_mod

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(storage_mod, "STORAGE_ROOT", Path(td))
        monkeypatch.setattr(storage_mod, "storage_path", lambda key: Path(td) / key)
        result = ingest_version(
            db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
            filename="fixture-scanned.pdf", data=_load("fixture-scanned.pdf"),
        )
    assert result["failed"] is True
    assert result["error_class"] == "no_text_layer"
    assert "第 1 页" in result["error_detail"] or "[1]" in result["error_detail"]
    assert "无可抽取文本" in result["error_detail"]


def test_table_pdf_header_footer_never_enter_chunks(db_session, base_row, monkeypatch):
    """页眉/页脚（含逐页变化的页码）不得进入任何业务 chunk。"""
    import tempfile
    from evidence_rag import storage as storage_mod

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(storage_mod, "STORAGE_ROOT", Path(td))
        monkeypatch.setattr(storage_mod, "storage_path", lambda key: Path(td) / key)
        result = ingest_version(
            db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
            filename="fixture-table.pdf", data=_load("fixture-table.pdf"),
        )
    assert result["failed"] is False and result["n_chunks"] > 0
    contents = _chunks_for(db_session, result["build_id"])
    joined = "\n".join(contents)
    assert "FIXTURE-A-001" not in joined, "页眉进入正文 chunk"
    assert "共 # 页" not in joined and "共 2 页" not in joined, "页脚进入正文 chunk"
    assert "必需材料 对应处理时限" not in joined, "跨页重复表头被当成数据行"


def test_table_pdf_crosspage_row_stays_associated(db_session, base_row, monkeypatch):
    """L30 的参数与依据条款必须共存于同一 chunk（行不因跨页被拆散）。"""
    import tempfile
    from evidence_rag import storage as storage_mod

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(storage_mod, "STORAGE_ROOT", Path(td))
        monkeypatch.setattr(storage_mod, "storage_path", lambda key: Path(td) / key)
        result = ingest_version(
            db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
            filename="fixture-table.pdf", data=_load("fixture-table.pdf"),
        )
    contents = _chunks_for(db_session, result["build_id"])
    host = next((c for c in contents if "L30" in c), None)
    assert host is not None, "L30 行丢失——跨页内容被静默丢弃"
    assert "A-R-02" in host and "3 个工作日" in host, "L30 的参数与依据条款被分离"


def test_messy_txt_fullwidth_searchable_and_clause_rejoined(db_session, base_row, monkeypatch):
    """脏 TXT：全角归一后可检索命中；被换行切断的条款号重组为单个编号。"""
    import tempfile
    from evidence_rag import storage as storage_mod

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(storage_mod, "STORAGE_ROOT", Path(td))
        monkeypatch.setattr(storage_mod, "storage_path", lambda key: Path(td) / key)
        result = ingest_version(
            db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
            filename="fixture-messy.txt", data=_load("fixture-messy.txt"),
        )
    assert result["failed"] is False and result["n_chunks"] > 0
    joined = "\n".join(_chunks_for(db_session, result["build_id"]))
    assert "HRC60" in joined, "全角 ＨＲＣ６０ 归一后应可命中"
    assert "3 个工作日" in joined or "3个工作日" in joined, "全角数字归一后应可命中"
    assert "2026-10-21" in joined
    assert "A-X-13" in joined, "断行条款号应重组为 A-X-13"
    assert "A-X-\n13" not in joined and "A-X- 13" not in joined, "条款号仍处于断开状态"


def test_every_fixture_chunk_carries_locator(db_session, base_row, monkeypatch):
    """三个格式夹具产生的每个 chunk 都必须带可用定位（页码/段落/标题路径）。"""
    import tempfile
    from evidence_rag import storage as storage_mod

    cases = [("fixture-table.pdf", "page"), ("fixture-messy.txt", "para")]
    for fname, key in cases:
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setattr(storage_mod, "STORAGE_ROOT", Path(td))
            monkeypatch.setattr(storage_mod, "storage_path", lambda key_: Path(td) / key_)
            result = ingest_version(
                db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                filename=fname, data=_load(fname),
            )
        rows = db_session.execute(
            select(Chunk).where(Chunk.index_build_id == result["build_id"])
        ).scalars().all()
        assert rows, f"{fname} 未产出任何 chunk"
        for row in rows:
            members = row.locator["members"]
            assert members and all(m.get(key) is not None for m in members), \
                f"{fname} 存在无 {key} 定位的 chunk: {row.locator}"
