#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建本地演示账号。

用法（仓库根目录）：
    .venv/Scripts/python.exe scripts/create_local_user.py <用户名> <密码> [--admin-all]

--admin-all：把该账号设为现有全部知识库的管理员（本地演示便利；生产环境
成员管理走 S2-T06 之后的正式流程，不走本脚本）。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from sqlalchemy import select  # noqa: E402

from evidence_rag.auth import hash_password  # noqa: E402
from evidence_rag.db import SessionLocal  # noqa: E402
from evidence_rag.models import KnowledgeBase, Membership, User  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    admin_all = "--admin-all" in sys.argv
    if len(args) < 2:
        print("用法：create_local_user.py <用户名> <密码> [--admin-all]")
        return 2
    username, password = args[0], args[1]
    if len(password) < 8:
        print("拒绝：密码至少 8 位（本地演示也要养成习惯）")
        return 2

    session = SessionLocal()
    exists = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists is not None:
        print(f"账号已存在：{username}（未改动；如需重置密码请先删除该用户行）")
        session.close()
        return 1
    user = User(username=username, password_hash=hash_password(password), display_name=username)
    session.add(user)
    session.flush()
    if admin_all:
        for kb in session.execute(select(KnowledgeBase)).scalars():
            session.add(Membership(user_id=user.id, kb_id=kb.id, role="admin"))
        session.flush()
    session.commit()
    kbs = session.execute(
        select(Membership.kb_id).where(Membership.user_id == user.id)
    ).scalars().all()
    print(f"已创建：{username}（管理员于知识库 {kbs}）")
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
