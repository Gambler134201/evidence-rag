"""FastAPI 应用工厂（S1-T01 骨架 → S1-T06 挂载问答路由）。

阶段 1 边界：问答路由无认证（local_user_id 仅本地竖切片用），S2-T01/02 接入
登录与服务端授权后替换；在此之前页面只允许本地合成数据（backlog S1-T08 条件 3）。
"""
from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import engine, get_session
from .models import QueryRun
from .providers import get_clients
from .rag import answer_question


class QueryIn(BaseModel):
    question: str
    top_k: int = 5
    # 阶段 1 本地竖切片的临时身份；不是认证，不得对外部署。
    local_user_id: int = 1


def create_app() -> FastAPI:
    app = FastAPI(title="evidence-rag API", version="0.1.0")

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        # 存活探针：不依赖数据库，进程活着即返回。
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> dict[str, str]:
        # 就绪探针：数据库必须可查询，失败显式 503（fail-loud，不静默装健康）。
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — 探针必须返回可读失败原因
            return {"status": "db_unreachable", "detail": str(exc)[:200]}
        return {"status": "ready"}

    @app.post("/knowledge-bases/{kb_id}/queries", tags=["qa"])
    def query_kb(kb_id: int, body: QueryIn, session: Session = Depends(get_session)) -> dict:
        # 真实/mock 客户端由 ENABLE_REAL_MODEL_CALLS 决定（fail-closed）。
        generation, embedder = get_clients()
        return answer_question(
            session,
            kb_id=kb_id,
            user_id=body.local_user_id,
            question=body.question,
            generation=generation,
            embedder=embedder,
            top_k=body.top_k,
        )

    @app.get("/query-runs/{run_id}", tags=["qa"])
    def get_run(run_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
        run = session.get(QueryRun, run_id)
        if run is None:
            # 404 口径：不存在与不可见不区分（无权限对象同样 404，S2-T02 生效）。
            raise HTTPException(status_code=404, detail="not found")
        return {
            "run_id": str(run.id),
            "kb_id": run.kb_id,
            "question": run.question,
            "status": run.status,
            "segments": run.answer_segments,
            "error_class": run.error_class,
            "retrieval_ms": run.retrieval_ms,
            "generation_ms": run.generation_ms,
            "total_ms": run.total_ms,
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "cost_note": run.cost_note,
        }

    return app


app = create_app()
