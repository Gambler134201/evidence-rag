"""认证与会话（S2-T01）。

设计要点（对应 backlog S2-T01 与实施方案 §6）：
- 密码哈希用标准库 PBKDF2-HMAC-SHA256（20 万次迭代 + 16 字节盐），不自创算法；
- 会话为服务端记录（sessions 表），Cookie 仅携带不可猜测的 UUID，HttpOnly +
  SameSite=Lax，Secure 在公开部署时随 HTTPS 打开；
- 登录失败统一"用户名或密码错误"，不区分账号不存在与密码错误（防枚举）；
- 未登录访问受保护接口 401；无权限对象 404（不存在与不可见不区分，S2-T02）。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import Session as SessionRow
from .models import User

SESSION_COOKIE = "evidence_rag_session"
SESSION_TTL_HOURS = 24
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(session: Session, user_id: int) -> SessionRow:
    row = SessionRow(
        id=uuid.uuid4(),
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
    )
    session.add(row)
    session.flush()
    return row


def set_session_cookie(response: Response, session_row: SessionRow) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        str(session_row.id),
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
        # Secure 标志在公开 HTTPS 部署时打开；本地 http 演示先不加，否则浏览器不回传。
    )


def login(session: Session, username: str, password: str, response: Response) -> User:
    user = session.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    ).scalar_one_or_none()
    # 用户不存在也走一次哈希比较，时间曲线一致（防用户名枚举的廉价近似）。
    stored = user.password_hash if user else hash_password("dummy-password-for-timing")
    ok = verify_password(password, stored)
    if user is None or not ok:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    row = create_session(session, user.id)
    set_session_cookie(response, row)
    return user


def logout(session: Session, session_id: uuid.UUID) -> None:
    row = session.get(SessionRow, session_id)
    if row is not None:
        row.revoked_at = datetime.now(timezone.utc)
        session.flush()


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """FastAPI 依赖：未登录/会话无效/过期/已撤销一律 401，不泄露原因细节。"""
    if not session_id:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="未登录")
    row = session.get(SessionRow, sid)
    now = datetime.now(timezone.utc)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=401, detail="未登录")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="未登录")
    request.state.session_id = sid
    return user
