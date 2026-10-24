"""应用配置：从仓库根 .env 读取，只在本模块集中解析一次。

设计约束（对应 docs/implementation-plan.md §8）：生成模型与 Embedding 是两个
独立配置项，代码中不共用一个"模型"开关；真实调用受 ENABLE_REAL_MODEL_CALLS
显式控制，默认关闭（S1-T11 的 mock 测试策略）。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# dev 布局：services/api/evidence_rag/config.py → 仓库根在 parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── PostgreSQL（本项目专用实例，docker-compose.yml）──
    postgres_user: str = "evidence_rag"
    postgres_password: str = ""
    postgres_db: str = "evidence_rag"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # ── 生成模型（用户本地自部署，OpenAI 兼容端点）──
    generation_base_url: str = ""
    generation_model: str = ""
    generation_api_key: str = ""

    # ── Embedding（硅基流动 bge-m3 免费档）──
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_dimension: int = 1024

    # ── 真实模型调用显式开关（默认关闭；测试一律走 mock）──
    enable_real_model_calls: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:"
            f"{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
