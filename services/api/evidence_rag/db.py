"""数据库访问：同步 SQLAlchemy 2.0 引擎与会话。

取舍记录（面试可答）：小语料、单体内、链路优先讲清楚，首期用同步引擎 +
FastAPI 线程池路由；是否切 async 由真实延迟数据决定，不预先引入复杂度。
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def make_engine(database_url: str | None = None):
    settings = get_settings()
    return create_engine(
        database_url or settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


engine = make_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个会话。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
