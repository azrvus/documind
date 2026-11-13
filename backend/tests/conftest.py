import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, openai_api_key=None, allowed_origins="http://localhost:3003")
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "provider_status", "unverified")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    return TestClient(main.app)


def workspace():
    return "00000000-0000-4000-8000-000000000001"
