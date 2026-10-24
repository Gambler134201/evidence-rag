"""日志/导出敏感信息脱敏（S2-T09）。

错误详情、日志与导出内容在落库/输出前统一过 redact()：任何 bearer 令牌、
API 密钥（sk- 开头）、password/authorization 字段值、连接串凭据一律遮蔽。
测试断言：脱敏规则生效 + 任何接口响应不回传密码哈希。
"""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-***"),
    (re.compile(r"(password\s*[=:]\s*)\S+", re.I), r"\1***"),
    (re.compile(r"(authorization\s*[=:]\s*)\S+", re.I), r"\1***"),
    (re.compile(r"(postgres(?:ql)?\+?\w*://[^:/\s]+:)[^@\s]+@", re.I), r"\1***@"),
    (re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.I), r"\1***"),
]


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out
