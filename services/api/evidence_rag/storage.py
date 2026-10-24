"""原始文件存储：项目专用文件卷（仓库 /storage，已 gitignore），键不可猜测。

数据库只存 storage_key，不存路径；下载走单独授权接口（实施方案 §7）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from .config import REPO_ROOT

STORAGE_ROOT = REPO_ROOT / "storage"


def new_storage_key(fmt: str) -> str:
    """不可猜测的存储键：uuid4 + 扩展名。不含原始文件名（可能含敏感信息）。"""
    suffix = {"markdown": ".md", "txt": ".txt", "pdf": ".pdf"}.get(fmt, ".bin")
    return f"{uuid.uuid4().hex}{suffix}"


def storage_path(key: str) -> Path:
    return STORAGE_ROOT / key


def save_raw(key: str, data: bytes) -> None:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    path = storage_path(key)
    path.write_bytes(data)
