"""FastAPI 路由（S1 链路 + S2-T01/T02/T04 认证与授权）。

401/403/404 口径见 lifecycle.py 模块注释。上传/发布当前合并为一步
（本地切片自动发布，实施方案 §5 允许），分步确认在管理页任务中拆开。
"""
from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import auth, lifecycle
from .config import get_settings
from .db import engine, get_session
from .routes_kb import router as kb_router
from .models import Document, QueryRun
from .providers import get_clients
from .rag import answer_question


class LoginIn(BaseModel):
    username: str
    password: str


class QueryIn(BaseModel):
    question: str
    top_k: int = 5


def create_app() -> FastAPI:
    app = FastAPI(title="evidence-rag API", version="0.2.0")
    app.include_router(kb_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # 本地开发前端；公开部署另行收紧
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> dict[str, str]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — 探针必须返回可读失败原因
            return {"status": "db_unreachable", "detail": str(exc)[:200]}
        return {"status": "ready"}

    # ── 认证（S2-T01）─────────────────────────────────────────────
    @app.post("/auth/login", tags=["auth"])
    def login(body: LoginIn, response: Response, session: Session = Depends(get_session)) -> dict:
        user = auth.login(session, body.username, body.password, response)
        session.commit()
        return {"user_id": user.id, "username": user.username, "display_name": user.display_name}

    @app.post("/auth/logout", tags=["auth"])
    def logout(
        request: Request,
        response: Response,
        session: Session = Depends(get_session),
        user=Depends(auth.get_current_user),
    ) -> dict:
        auth.logout(session, request.state.session_id)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        session.commit()
        return {"status": "logged_out"}

    @app.get("/auth/me", tags=["auth"])
    def me(user=Depends(auth.get_current_user)) -> dict:
        return {"user_id": user.id, "username": user.username, "display_name": user.display_name}

    # ── 问答（S1 链路 + S2-T02 授权）──────────────────────────────
    @app.post("/knowledge-bases/{kb_id}/queries", tags=["qa"])
    def query_kb(
        kb_id: int,
        body: QueryIn,
        session: Session = Depends(get_session),
        user=Depends(auth.get_current_user),
    ) -> dict:
        lifecycle.require_kb_member(session, user.id, kb_id)
        generation, embedder = get_clients()
        settings = get_settings()
        result = answer_question(
            session, kb_id=kb_id, user_id=user.id, question=body.question,
            generation=generation, embedder=embedder, top_k=body.top_k,
            min_score=settings.retrieval_refuse_score,
            warn_score=settings.retrieval_warn_score,
        )
        session.commit()
        return result

    @app.get("/query-runs/{run_id}", tags=["qa"])
    def get_run(
        run_id: uuid.UUID,
        session: Session = Depends(get_session),
        user=Depends(auth.get_current_user),
    ) -> dict:
        run = lifecycle.require_run_access(session, user.id, run_id)
        session.commit()
        return {
            "run_id": str(run.id), "kb_id": run.kb_id, "question": run.question,
            "status": run.status, "segments": run.answer_segments,
            "error_class": run.error_class, "retrieval_ms": run.retrieval_ms,
            "generation_ms": run.generation_ms, "total_ms": run.total_ms,
            "prompt_tokens": run.prompt_tokens, "completion_tokens": run.completion_tokens,
            "cost_note": run.cost_note,
        }

    @app.get("/chunks/{chunk_id}", tags=["qa"])
    def get_chunk(
        chunk_id: int,
        session: Session = Depends(get_session),
        user=Depends(auth.get_current_user),
    ) -> dict:
        chunk = lifecycle.require_chunk_access(session, user.id, chunk_id)
        session.commit()
        return {
            "chunk_id": chunk.id, "version_id": chunk.version_id,
            "locator": chunk.locator, "content": chunk.content,
        }

    # ── 管理：上传/列表/详情/发布/重试 → routes_kb.py（APIRouter）

    @app.patch("/documents/{document_id}", tags=["admin"])
    def patch_document(
        document_id: int,
        active: bool = Form(...),
        session: Session = Depends(get_session),
        user=Depends(auth.get_current_user),
    ) -> dict:
        # 管理操作按"该文档所属知识库的管理员"校验（先取文档再校验角色）。
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="not found")
        lifecycle.require_kb_admin(session, user.id, doc.kb_id)
        lifecycle.set_document_active(session, document_id=document_id,
                                      active=active, actor_user_id=user.id)
        session.commit()
        return {"document_id": document_id, "active": active}

    return app


app = create_app()
