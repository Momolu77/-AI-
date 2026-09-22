from datetime import UTC, datetime

import pytest
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        database=tmp_path / "data/app.db",
        secret="test-only-" + "s" * 48,
        env="test",
        first_token_timeout=0.05,
        total_timeout=5,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.app.state.core.seed()
        yield client


def enter(client, seat="01"):
    core = client.app.state.core
    token = core.seed()[seat]
    result = client.post("/api/v1/session/bootstrap", json={"seat": seat, "token": token})
    assert result.status_code == 200, result.text
    info = result.json()
    return info, {"Authorization": "Bearer " + info["token"]}


def now():
    return datetime.now(UTC).isoformat()
