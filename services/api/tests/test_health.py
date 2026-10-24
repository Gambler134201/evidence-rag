"""S1-T01 骨架验收：健康检查与配置装载（不涉及业务表）。"""
from fastapi.testclient import TestClient

from evidence_rag.config import get_settings
from evidence_rag.main import create_app


def test_healthz_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok_against_live_db():
    client = TestClient(create_app())
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_settings_read_from_env():
    settings = get_settings()
    # 连接串指向本项目专用库；不断言密码等敏感值。
    assert settings.database_url.startswith("postgresql+psycopg://evidence_rag:")
    assert settings.database_url.endswith("@localhost:5432/evidence_rag")
    # 真实调用开关默认必须关闭（S1-T11 约定）。
    assert settings.enable_real_model_calls is False
