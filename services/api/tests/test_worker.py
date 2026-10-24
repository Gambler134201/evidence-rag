"""S2-T05 验收：任务后台进程的认领互斥、租约恢复、断点续跑与重试退避。

生产流程是 claim → run；测试同样按此顺序，退避时间用"手动清零 next_retry_at"
模拟时间流逝（同时恰好覆盖认领过滤条件的正确性）。
"""
import uuid as _uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from evidence_rag import worker
from evidence_rag.models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexBuild,
    IngestionJob,
    KnowledgeBase,
)
from evidence_rag.providers import MockEmbedding

MD_MANY = "# 长文档\n\n" + "\n\n".join(
    f"## 段落 {i}\n\nA-Z{i}-0{i} " + ("这是用于撑满分块上限的占位句子。" * 28)
    for i in range(1, 6)
) + "\n"


class CountingEmbedder(MockEmbedding):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return super().embed(texts)


class FlakyEmbedder(MockEmbedding):
    """第 N 次调用抛错的 Embedding（模拟外部接口故障/进程中断）。"""

    def __init__(self, fail_on_call: int | None):
        super().__init__()
        self.calls = 0
        self.fail_on_call = fail_on_call

    def embed(self, texts):
        self.calls += 1
        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise RuntimeError("simulated embedding outage")
        return super().embed(texts)


@pytest.fixture()
def env(migrated_engine, monkeypatch, tmp_path):
    session = sessionmaker(bind=migrated_engine)()
    tag = _uuid.uuid4().hex[:8]
    kb = KnowledgeBase(name=f"kb-{tag}", slug=f"kb-{tag}")
    session.add(kb)
    session.flush()
    doc = Document(kb_id=kb.id, title="长文档")
    session.add(doc)
    session.flush()
    # 存储重定向到临时目录（worker 的 enqueue/save 与读取都经此路径）
    monkeypatch.setattr(worker, "save_raw",
                        lambda key, data: (tmp_path / key).write_bytes(data))
    monkeypatch.setattr(worker, "storage_path", lambda key: tmp_path / key)
    # 测试库跨用例复用：先清空前面用例遗留的排队任务，保证认领从本用例开始
    worker.run_pending_jobs(session, MockEmbedding())
    yield {"session": session, "kb": kb.id, "doc": doc.id, "tmp": tmp_path}
    session.close()


def _enqueue(env, data=MD_MANY.encode("utf-8"), filename="长文档.md"):
    return worker.enqueue_ingest(env["session"], kb_id=env["kb"], document_id=env["doc"],
                                 filename=filename, data=data)


def _state(env, job_id):
    j = env["session"].get(IngestionJob, job_id)
    v = env["session"].get(DocumentVersion, j.version_id)
    b = env["session"].get(IndexBuild, j.build_id)
    return j, v, b


def _claim_and_run(env, embedder):
    """生产语义：先认领再执行。返回 (state, job_id)。"""
    job = worker.claim_job(env["session"])
    if job is None:
        return None, None
    state = worker.run_job(env["session"], job.id, embedder)
    return state, job.id


def _expire_backoff(env, job_id):
    """模拟退避时间流逝，让任务立即可被再次认领。"""
    env["session"].execute(
        text("UPDATE ingestion_jobs SET next_retry_at = NULL WHERE id = :i"),
        {"i": job_id},
    )
    env["session"].commit()


def test_enqueue_creates_draft_rows_and_worker_completes(env):
    r = _enqueue(env)
    assert r["reused"] is False and r["duplicate"] is False
    j, v, b = _state(env, r["job_id"])
    assert j.status == "queued" and v.status == "draft" and b.status == "pending"
    state, _ = _claim_and_run(env, MockEmbedding())
    assert state == "succeeded"
    j, v, b = _state(env, r["job_id"])
    assert (j.status, v.status, b.status) == ("succeeded", "ready", "ready")
    with_vec = env["session"].execute(
        select(Chunk).where(Chunk.index_build_id == b.id, Chunk.embedding.isnot(None))
    ).scalars().all()
    assert len(with_vec) == b.total_chunks, "全部 chunk 必须带向量"


def test_enqueue_duplicate_active_job(env):
    first = _enqueue(env)
    second = _enqueue(env)
    assert second["duplicate"] is True
    assert second["job_id"] == first["job_id"], "同内容同配置只允许一个活动任务"


def test_enqueue_reuses_ready_build_without_new_job(env):
    first = _enqueue(env)
    state, _ = _claim_and_run(env, MockEmbedding())
    assert state == "succeeded"
    second = _enqueue(env)
    assert second["reused"] is True and second["job_id"] is None
    assert second["build_id"] == first["build_id"]


def test_claim_is_exclusive_across_sessions(env):
    _enqueue(env)
    _enqueue(env, "# 另一份\n\n## 条款\n\nA-Y9-01 第二个任务的内容，足够特别。\n".encode("utf-8"),
             filename="另一份.md")
    s1 = env["session"]
    s2 = sessionmaker(bind=s1.bind)()
    j1 = worker.claim_job(s1)
    j2 = worker.claim_job(s2)
    assert j1 is not None and j2 is not None and j1.id != j2.id
    assert worker.claim_job(s1) is None, "两条任务被认领后，第三次认领应为空"
    assert j1.status == "running" and j1.attempt == 1 and j1.lease_until is not None
    s2.close()


def test_lease_reaper_requeues_expired_job(env):
    r = _enqueue(env)
    job = worker.claim_job(env["session"])
    assert job.status == "running"
    # 模拟进程崩溃：租约无人续期，人为回拨到过去
    env["session"].execute(
        text("UPDATE ingestion_jobs SET lease_until = now() - interval '1 minute' WHERE id = :i"),
        {"i": job.id},
    )
    env["session"].commit()
    assert worker.reap_expired(env["session"]) == 1
    j = env["session"].get(IngestionJob, r["job_id"])
    assert j.status == "queued", "租约过期必须回到队列"
    again = worker.claim_job(env["session"])
    assert again is not None and again.id == r["job_id"]


def test_resume_after_embed_crash_only_redoes_remaining_batches(env, monkeypatch):
    """断点续跑：Embedding 中途崩溃后，重试只补剩余批次，不重复已成功调用。"""
    monkeypatch.setattr(worker, "EMBED_BATCH", 2)  # 5 段 → 3 批（2+2+1）
    r = _enqueue(env)
    flaky = FlakyEmbedder(fail_on_call=2)  # 第 2 批崩溃（第 1 批已成功提交）
    state, job_id = _claim_and_run(env, flaky)
    assert state == "queued", "Embedding 故障应回到队列等待重试"
    j, _, _ = _state(env, job_id)
    assert j.progress["embedded_until"] == 2, "已完成的第 1 批进度必须持久化"
    assert j.error_class == "embedding_error"
    first_calls = flaky.calls

    _expire_backoff(env, job_id)
    good = CountingEmbedder()
    state2, _ = _claim_and_run(env, good)
    assert state2 == "succeeded"
    j, v, b = _state(env, job_id)
    assert j.progress["embedded_until"] == b.total_chunks
    # 剩余 3 条 chunk（batch=2）= 2 批：只补剩余，不重做已成功的第 1 批
    assert good.calls == 2, "续跑只应补做剩余批次"
    assert first_calls == 2


def test_unparseable_upload_fails_visibly(env):
    r = worker.enqueue_ingest(env["session"], kb_id=env["kb"], document_id=env["doc"],
                              filename="broken.pdf", data=b"not-a-pdf")
    state, _ = _claim_and_run(env, MockEmbedding())
    assert state == "failed"
    j, v, b = _state(env, r["job_id"])
    assert j.error_class == "corrupt_file" and v.status == "failed"
    assert b.status == "failed"


def test_retry_backoff_then_failed_after_max_attempts(env):
    r = _enqueue(env)
    always = FlakyEmbedder(fail_on_call=None)

    def always_fail(texts):
        raise RuntimeError("provider down")

    always.embed = always_fail
    results = []
    for _ in range(worker.MAX_ATTEMPTS):
        state, job_id = _claim_and_run(env, always)
        results.append(state)
        if state == "queued":
            j, _, _ = _state(env, job_id)
            assert j.next_retry_at is not None, "重排必须带退避时间"
            _expire_backoff(env, job_id)
    assert results == ["queued", "queued", "failed"], "两次退避重试后必须置 failed"
