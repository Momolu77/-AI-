import uuid
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
    entry = client.post("/api/v1/entry/bootstrap", json={"seat": seat, "token": token}).json()
    headers = {"Authorization": "Bearer " + entry["token"], "X-Writer-Id": "test-writer-" + seat}
    result = client.post(
        "/api/v1/session/bootstrap",
        headers=headers,
        json={
            "task_id": entry["tasks"][0]["task_id"],
            "assignment_id": entry["tasks"][0]["assignment_id"],
            "writer_id": "test-writer-" + seat,
        },
    )
    assert result.status_code == 200, result.text
    info = result.json()
    headers["Authorization"] = "Bearer " + info["token"]
    if info["status"] == "PREPARING":
        task = client.get("/api/v1/tasks/" + info["task_id"], headers=headers).json()
        result = client.post(
            "/api/v1/session/prerequisite",
            headers=headers,
            json={
                **occurrence(),
                "version": task["prerequisite"]["version"],
                "responses": [
                    {"question_id": q["id"], "answer_value": q["options"][0]["value"]}
                    for q in task["prerequisite"]["questions"]
                ],
            },
        )
        assert result.status_code == 200, result.text
        result = client.post("/api/v1/session/start", headers=headers, json=occurrence())
        assert result.status_code == 200, result.text
        info = {**result.json(), "token": info["token"]}
    return info, headers


def occurrence():
    return {
        "event_id": str(uuid.uuid4()),
        "occurred_at": now(),
        "transport": {
            "producer_id": "test-browser",
            "producer_seq": 1,
            "raw_time": now(),
            "monotonic_ms": 1,
            "clock_calibration_id": None,
            "time_source": "client_clock",
            "causal_parent_ids": [],
        },
    }


def now():
    return datetime.now(UTC).isoformat()
