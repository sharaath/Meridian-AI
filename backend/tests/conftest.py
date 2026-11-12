"""Pytest fixtures for isolated backend API testing."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session")
def test_client(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("meridian_test")
    db_file = db_dir / "test.db"
    storage_dir = db_dir / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    os.environ["ENVIRONMENT"] = "test"
    os.environ["SECRET_KEY"] = "test-secret-key-for-automated-suite-32chars"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"
    os.environ["LOCAL_STORAGE_DIR"] = str(storage_dir)
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_ANON_KEY"] = ""
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
    os.environ["RATE_LIMIT_PER_MINUTE"] = "200"

    from app.config import get_settings
    get_settings.cache_clear()

    from app.database import init_db
    init_db()

    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client


def register_and_auth(client: TestClient, email: str, username: str, password: str = "StrongPass123!") -> dict:
    res = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {
        "user": data["user"],
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }

