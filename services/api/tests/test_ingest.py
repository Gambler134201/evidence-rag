"""S1-T03/T04 验收：上传校验、错误分类、解析定位、分块与去重（对真实测试库）。"""
import subprocess
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import REPO_ROOT

from evidence_rag import storage
from evidence_rag.errors import IngestError
from evidence_rag.ingest import ingest_version
from evidence_rag.models import Chunk, DocumentVersion, IndexBuild

MD_SAMPLE = (
    "# 交付规则\n\n"
    "## 验收期限\n\n"
    "接收方应从完整交付的次一工作日起 3 个工作日内给出验收意见，"
    "截止为最后一日 18:00。逾期未收到意见的，交付方应发送一次书面提醒。\n"
    "提醒后的次一工作日起再等待 2 个工作日，仍无回复可登记人工协调。MARKER-A。\n\n"
    "## 退回整改\n\n"
    "再次提交须包含原验收项清单、问题证据、修复说明、对应新交付物与尚未解决项说明。"
    "材料齐全后重新按验收期限计算。MARKER-B 在这一段里，"
    + "这一句用来把段落拉长以便触发分块上限。"*12
    + "MARKER-C 收尾。\n"
)


@pytest.fixture()
def db_session(migrated_engine):
    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def tmp_storage(monkeypatch, tmp_path):
    """存储重定向到临时目录；仓库 /storage 仍被 gitignore（另有专项断言）。"""
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(storage, "storage_path", lambda key: tmp_path / key)


@pytest.fixture()
def base_row(db_session):
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:8]
    from evidence_rag.models import Document, KnowledgeBase

    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    db_session.add(kb)
    db_session.flush()
    doc = Document(kb_id=kb.id, title="交付规则")
    db_session.add(doc)
    db_session.flush()
    return {"kb": kb.id, "doc": doc.id}


# ── S1-T03：类型/校验/错误分类 ────────────────────────────────────────────

def test_unsupported_type_rejected(db_session, base_row, tmp_storage):
    with pytest.raises(IngestError) as e:
        ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                       filename="规则.docx", data=b"PK\x03\x04")
    assert e.value.error_class == "unsupported_type"


def test_empty_file_rejected(db_session, base_row, tmp_storage):
    with pytest.raises(IngestError) as e:
        ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                       filename="a.txt", data=b"")
    assert e.value.error_class == "empty_file"


def test_oversized_rejected_not_reported_as_scanned(db_session, base_row, tmp_storage):
    with pytest.raises(IngestError) as e:
        ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                       filename="big.txt", data=b"\x00" * (10 * 1024 * 1024 + 1))
    assert e.value.error_class == "oversized"


def test_corrupt_pdf_fails_visibly(db_session, base_row, tmp_storage):
    """解析失败不抛穿：返回 failed 结果，行状态可读（backlog 条件 4）。"""
    result = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="broken.pdf", data=b"not-a-pdf-at-all")
    assert result["failed"] is True
    assert result["error_class"] == "corrupt_file"
    assert "解析失败" in result["error_detail"]
    build = db_session.get(IndexBuild, result["build_id"])
    assert build.status == "failed" and build.total_chunks is None


def test_whitespace_only_text_is_empty_text_not_success(db_session, base_row, tmp_storage):
    """backlog S1-T03 条件 2：空文本不得记为索引成功。"""
    result = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="blank.txt", data="  \n\r\n \t ".encode("utf-8"))
    assert result["failed"] is True and result["error_class"] == "empty_text"
    ver = db_session.get(DocumentVersion, result["version_id"])
    assert ver.status == "failed", "空文本版本必须停在 failed，不得 ready"
    n_chunks = db_session.execute(
        select(Chunk).where(Chunk.index_build_id == result["build_id"])
    ).scalars().all()
    assert n_chunks == []


def test_storage_never_tracked_by_git(tmp_storage):
    """backlog S1-T03 条件 5：原始上传不进 Git（/storage/ 在 .gitignore）。"""
    probe = REPO_ROOT / "storage" / f"probe-{uuid.uuid4().hex}.tmp"
    probe.parent.mkdir(exist_ok=True)
    probe.write_bytes(b"x")
    try:
        rc = subprocess.run(["git", "check-ignore", "-q", str(probe.relative_to(REPO_ROOT))],
                            cwd=REPO_ROOT).returncode
        assert rc == 0, "storage/ 未被 gitignore 覆盖"
    finally:
        probe.unlink(missing_ok=True)


# ── S1-T03：去重与指纹 ───────────────────────────────────────────────────

def test_dedup_reuses_ready_build_without_reembedding(db_session, base_row, tmp_storage):
    from evidence_rag.providers import MockEmbedding

    class CountingEmbedder(MockEmbedding):
        calls = 0

        def embed(self, texts):
            CountingEmbedder.calls += 1
            return super().embed(texts)

    embedder = CountingEmbedder()
    first = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                           filename="a.md", data=MD_SAMPLE.encode("utf-8"), embedder=embedder)
    assert first["reused"] is False and first["n_chunks"] > 0
    second = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="a.md", data=MD_SAMPLE.encode("utf-8"), embedder=embedder)
    assert second["reused"] is True
    assert second["build_id"] == first["build_id"]
    assert CountingEmbedder.calls == 1, "复用构建时不得再次发起 Embedding"


def test_config_change_creates_new_build_keeps_old(db_session, base_row, tmp_storage):
    first = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                           filename="a.md", data=MD_SAMPLE.encode("utf-8"),
                           chunk_config={"max_chars": 400})
    second = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="a.md", data=MD_SAMPLE.encode("utf-8"),
                            chunk_config={"max_chars": 600})
    assert second["reused"] is False and second["build_id"] != first["build_id"]
    builds = db_session.execute(
        select(IndexBuild).where(IndexBuild.version_id.in_(
            select(DocumentVersion.id).where(DocumentVersion.document_id == base_row["doc"])
        ))
    ).scalars().all()
    assert len(builds) == 2 and all(b.status == "ready" for b in builds), "旧构建记录必须保留"


# ── S1-T04：解析、定位、分块 ─────────────────────────────────────────────

def test_md_chunks_have_title_path_and_prefix(db_session, base_row, tmp_storage):
    result = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="a.md", data=MD_SAMPLE.encode("utf-8"))
    chunks = db_session.execute(
        select(Chunk).where(Chunk.index_build_id == result["build_id"]).order_by(Chunk.ordinal)
    ).scalars().all()
    assert any("交付规则" in c.locator["title_path"] for c in chunks)
    assert any(c.content.startswith("[验收期限]") for c in chunks), "标题前缀应进入块内容"


def test_every_chunk_locatable(db_session, base_row, tmp_storage):
    """backlog S1-T04 条件 1：每个 chunk 的 locator 能指回原文位置。"""
    result = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="a.md", data=MD_SAMPLE.encode("utf-8"))
    chunks = db_session.execute(
        select(Chunk).where(Chunk.index_build_id == result["build_id"])
    ).scalars().all()
    raw_len = len(MD_SAMPLE)
    for c in chunks:
        members = c.locator["members"]
        assert members, "chunk 必须记录成员块的定位"
        for m in members:
            s, e = m["source_chars"]
            assert 0 <= s < e <= raw_len, f"locator 字符区间越界: {m}"


def test_chunking_no_silent_truncation(db_session, base_row, tmp_storage):
    """backlog S1-T04 条件 3 前提：切分不得丢内容——首尾标记必须都能检索到。"""
    result = ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                            filename="a.md", data=MD_SAMPLE.encode("utf-8"))
    all_text = "".join(
        db_session.execute(
            select(Chunk.content).where(Chunk.index_build_id == result["build_id"])
        ).scalars()
    )
    for marker in ("MARKER-A", "MARKER-B", "MARKER-C", "3 个工作日"):
        assert marker in all_text, f"切分丢失内容: {marker}"


def test_invalid_chunk_config_rejected_before_any_rows(db_session, base_row, tmp_storage):
    before = db_session.execute(select(DocumentVersion.id)).scalars().all()
    with pytest.raises(ValueError):
        ingest_version(db_session, kb_id=base_row["kb"], document_id=base_row["doc"],
                       filename="a.md", data=MD_SAMPLE.encode("utf-8"),
                       chunk_config={"max_chars": 99999})
    after = db_session.execute(select(DocumentVersion.id)).scalars().all()
    assert before == after, "非法配置不得留下任何数据库痕迹"
