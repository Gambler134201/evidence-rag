"""模型客户端（S1-T11）：生成与 Embedding 各自独立配置，真实调用显式开关。

默认（ENABLE_REAL_MODEL_CALLS=0）一切走 mock：测试无网络、无密钥即可全绿；
真实客户端仅在开关打开时构造（S1-T10 基线与 S0-T06 连通记录共用此路径）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol

from ..config import get_settings


class GenerationClient(Protocol):
    def chat(self, system: str, user: str, *, max_tokens: int = 400, temperature: float = 0.0) -> str:
        ...


class EmbeddingClient(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAICompatGeneration:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.last_usage: dict | None = None

    def chat(self, system: str, user: str, *, max_tokens: int = 400, temperature: float = 0.0) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"}
            + ({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"generation_http_{exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"generation_unreachable: {exc.reason}") from exc
        self.last_usage = body.get("usage")
        return body["choices"][0]["message"]["content"]


class OpenAICompatEmbedding:
    def __init__(self, base_url: str, model: str, api_key: str = "", dimension: int = 1024, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.dimension = dimension
        self.timeout = timeout
        self.last_usage: dict | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        req = urllib.request.Request(
            self.base_url + "/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
            + ({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"embedding_http_{exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"embedding_unreachable: {exc.reason}") from exc
        self.last_usage = body.get("usage")
        vectors = [item["embedding"] for item in body["data"]]
        for v in vectors:
            if len(v) != self.dimension:
                raise RuntimeError(f"embedding_dimension_mismatch: got {len(v)}, expect {self.dimension}")
        return vectors


class MockEmbedding:
    """确定性 mock 向量：字符 bigram 哈希进 1024 维并归一。

    相似文本（字符重叠多）余弦更高，足以支撑检索排序类测试的语义；
    不伪造任何真实语义能力，测试结果一律标注 mock。
    """

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import math

        vectors = []
        for text in texts:
            vec = [0.0] * self.dimension
            for i in range(len(text) - 1):
                bigram = text[i : i + 2]
                h = int(hashlib.md5(bigram.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dimension] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


class MockGeneration:
    """可编程 mock 生成器：按注入规则返回脚本答案，供契约测试使用。"""

    def __init__(self, rules: list[tuple[str, str]] | None = None, default: str = ""):
        # rules: [(问题子串, 回复原文)]，按顺序首个命中者生效
        self.rules = rules or []
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str, *, max_tokens: int = 400, temperature: float = 0.0) -> str:
        self.calls.append((system, user))
        for needle, reply in self.rules:
            if needle in user:
                return reply
        return self.default


def get_clients() -> tuple[GenerationClient, EmbeddingClient]:
    """按配置返回客户端对；真实调用必须显式开开关（fail-closed）。"""
    settings = get_settings()
    if not settings.enable_real_model_calls:
        return MockGeneration(), MockEmbedding(settings.embedding_dimension)
    if not settings.generation_base_url or not settings.embedding_base_url:
        raise RuntimeError(
            "real_calls_enabled_but_unconfigured: .env 缺少 GENERATION_BASE_URL 或 EMBEDDING_BASE_URL"
        )
    return (
        OpenAICompatGeneration(
            settings.generation_base_url,
            settings.generation_model,
            settings.generation_api_key,
        ),
        OpenAICompatEmbedding(
            settings.embedding_base_url,
            settings.embedding_model,
            settings.embedding_api_key,
            settings.embedding_dimension,
        ),
    )
