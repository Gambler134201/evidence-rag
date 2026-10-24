"""FastAPI 应用工厂（S1-T01 骨架）。

当前只提供存活/就绪探针；业务路由按 backlog 顺序在 S1-T03 起逐步挂载。
"""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from .db import engine


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

    return app


app = create_app()
