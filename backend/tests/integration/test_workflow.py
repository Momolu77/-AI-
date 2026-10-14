import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.main import create_app
from app.services.exporting import backup, export_session, restore, validate_export
from fastapi.testclient import TestClient

from backend.tests.conftest import enter, now, occurrence


def identifier():
    return str(uuid.uuid4())


def event(name="planner_opened", payload=None, **extra):
    return {
        **occurrence(),
        "event_name": name,
        "actor": "student",
        "occurred_at": now(),
        "client_sequence_no": 1,
        "payload": payload or {},
        **extra,
    }


def send(client, headers, path, body):
    if path == "/session/end" and body is None:
        body = occurrence()
    if path in {"/workbench/preview/run", "/submissions"} or path.endswith("/interaction"):
        for key, value in occurrence().items():
            body.setdefault(key, value)
    result = client.post("/api/v1" + path, headers=headers, json=body)
    assert result.status_code == 200, result.text
    return result.json()


def test_session_event_outbox_idempotency_and_end(client):
    info, headers = enter(client)
    assert enter(client)[0]["id"] == info["id"]
    valid = event()
    forged = event("submit_succeeded", {"submission_id": "a", "snapshot_id": "b"}, actor="system")
    results = send(
        client,
        headers,
        "/events/batch",
        {"session_id": info["id"], "events": [valid, forged, event("unknown")]},
    )["results"]
    assert [r["status"] for r in results] == ["accepted", "rejected", "rejected"]
    assert (
        send(client, headers, "/events/batch", {"session_id": info["id"], "events": [valid]})[
            "results"
        ][0]["status"]
        == "accepted_duplicate"
    )
    conflicting = {**valid, "event_name": "submit_cancelled"}
    assert (
        send(client, headers, "/events/batch", {"session_id": info["id"], "events": [conflicting]})[
            "results"
        ][0]["status"]
        == "rejected"
    )
    old = event("window_left", {"leave_reason": "pagehide"})
    assert send(client, headers, "/session/end", None)["status"] == "ENDED"
    send(client, headers, "/session/end", None)
    assert (
        send(client, headers, "/events/batch", {"session_id": info["id"], "events": [old]})[
            "results"
        ][0]["status"]
        == "accepted"
    )
    assert (
        client.put(
            "/api/v1/workbench/code", headers=headers, json={"content": "x", "revision": 1}
        ).status_code
        == 409
    )
    assert enter(client)[0]["id"] != info["id"]
    core = client.app.state.core
    with core.db.read() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY sequence_no", (info["id"],)
        ).fetchall()
    assert [r["event_name"] for r in rows[:2]] == ["task_prerequisite_completed", "task_started"]
    assert [r["sequence_no"] for r in rows] == list(range(1, len(rows) + 1))
    assert sum(r["event_name"] == "task_ended" for r in rows) == 1


def test_revisions_runs_errors_isolation(client):
    one, h1 = enter(client)
    _, h2 = enter(client, "02")
    content = "<button onclick=\"throw new Error('click')\">测试😀</button>"
    saved = client.put(
        "/api/v1/workbench/code", headers=h1, json={"content": content, "revision": 1}
    ).json()
    run_command = {"content": content, "revision": 1, "run_id": identifier(), "occurred_at": now()}
    run = send(client, h1, "/workbench/preview/run", run_command)
    assert send(client, h1, "/workbench/preview/run", run_command)["run_id"] == run["run_id"]
    html = client.get(run["url"])
    assert (
        html.status_code == 200
        and content in html.text
        and "sandbox allow-scripts allow-forms" in html.headers["content-security-policy"]
        and "form-action 'none'" in html.headers["content-security-policy"]
        and "allow-same-origin" not in html.headers["content-security-policy"]
    )
    assert (client.app.state.core.settings.data_dir / saved["content_ref"]).read_text(
        encoding="utf-8"
    ) == content
    base = {"message_id": identifier(), "channel": run["channel"], "kind": "ready"}
    send(client, h1, f"/workbench/preview/{run['run_id']}/interaction", base)
    error = {
        "message_id": identifier(),
        "channel": run["channel"],
        "kind": "error",
        "text": "click",
        "error_phase": "interaction",
        "line": 1,
        "column": 2,
    }
    send(client, h1, f"/workbench/preview/{run['run_id']}/interaction", error)
    assert (
        client.post(
            f"/api/v1/workbench/preview/{run['run_id']}/interaction", headers=h2, json=base
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/workbench/preview/{run['run_id']}/logs", headers=h2).status_code == 404
    )
    assert (
        client.post(
            f"/api/v1/workbench/preview/{run['run_id']}/interaction",
            headers=h1,
            json={**base, "channel": "forged"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/workbench/code", headers=h1, json={"content": "changed", "revision": 1}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/workbench/state", headers=h2).json()["code"]["content"] == ""
    with client.app.state.core.db.read() as conn:
        names = [
            r[0]
            for r in conn.execute("SELECT event_name FROM events WHERE session_id=?", (one["id"],))
        ]
    assert all(name in names for name in ("preview_run", "preview_ready", "preview_error_detected"))


def ai_command(**kwargs):
    return {
        **occurrence(),
        "draft_revision": 0,
        "reference_ids": [],
        "base_code_revision": 0,
        "request_id": identifier(),
        "draft_id": identifier(),
        "message_text": "生成游戏",
        "attachment_ids": [],
        "retry_of_request_id": None,
        "occurred_at": now(),
        **kwargs,
    }


def finish_ai(client, header, request_id):
    response = client.get(f"/api/v1/ai/requests/{request_id}/stream", headers=header)
    assert response.status_code == 200
    data = [
        json.loads(block.split("data: ")[1])
        for block in response.text.split("\n\n")
        if block.startswith("event: done")
    ]
    assert len(data) == 1
    return data[0]


def test_attachment_real_parse_and_ai_stream(client):
    _, h1 = enter(client)
    _, h2 = enter(client, "02")
    attachment = client.post(
        "/api/v1/attachments",
        headers=h1,
        data={"attachment_id": identifier()},
        files={"file": ("unit.txt", "教材词汇 hello world".encode(), "text/plain")},
    ).json()
    assert (
        attachment["status"] == "READY" and attachment["extracted_text"] == "教材词汇 hello world"
    )
    assert client.get("/api/v1/attachments/" + attachment["id"], headers=h2).status_code == 404
    command = ai_command(message_text="", attachment_ids=[attachment["id"]])
    req = send(client, h1, "/ai/requests", command)
    assert send(client, h1, "/ai/requests", command)["id"] == req["id"]
    result = finish_ai(client, h1, req["id"])
    assert (
        result["request"]["status"] == "SUCCEEDED"
        and "已读取 1 个附件" in result["response"]["response_text"]
    )
    assert client.get(f"/api/v1/ai/requests/{req['id']}/stream", headers=h2).status_code == 404
    assert (
        client.post(
            "/api/v1/ai/requests", headers=h2, json=ai_command(attachment_ids=[attachment["id"]])
        ).status_code
        == 404
    )
    bad = client.post(
        "/api/v1/attachments",
        headers=h1,
        data={"attachment_id": identifier()},
        files={"file": ("bad.pdf", b"not a PDF", "application/pdf")},
    ).json()
    assert bad["status"] == "FAILED"
    assert (
        client.post(
            "/api/v1/ai/requests", headers=h1, json=ai_command(attachment_ids=[bad["id"]])
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "scenario,error_type,partial",
    [
        ("first_token_timeout", "FIRST_TOKEN_TIMEOUT", False),
        ("partial_then_error", "CONNECTION_LOST", True),
        ("rate_limited", "RATE_LIMITED", False),
    ],
)
def test_ai_failures_partial_and_explicit_retry(client, scenario, error_type, partial):
    info, headers = enter(client)
    client.app.state.core.settings.fake_scenario = scenario
    cmd = ai_command()
    req = send(client, headers, "/ai/requests", cmd)
    result = finish_ai(client, headers, req["id"])
    assert result["request"]["error"]["error_type"] == error_type
    assert bool(result["response"]["response_text"]) is partial
    client.app.state.core.settings.fake_scenario = "success"
    client.app.state.core.save(info["id"], "code", "<p>edited after failure</p>", 1)
    retry_cmd = ai_command(draft_id=cmd["draft_id"], retry_of_request_id=req["id"])
    retry = send(client, headers, f"/ai/requests/{req['id']}/retry", retry_cmd)
    assert retry["base_code"] == req["base_code"] == ""
    assert retry["id"] != req["id"] and retry["command"]["retry_of_request_id"] == req["id"]
    assert finish_ai(client, headers, retry["id"])["request"]["status"] == "SUCCEEDED"


def submission(code="作品 A", revision=1, **extra):
    return {
        **occurrence(),
        "submission_id": identifier(),
        "snapshot_id": identifier(),
        "code": code,
        "plan": "计划\n中文😀",
        "code_revision": revision,
        "plan_revision": 1,
        "occurred_at": now(),
        **extra,
    }


def test_submission_immutable_export_backup_restore(client, tmp_path):
    info, headers = enter(client)
    command = submission()
    result = send(client, headers, "/submissions", command)
    assert result["status"] == "SUCCEEDED"
    assert send(client, headers, "/submissions", command)["id"] == result["id"]
    assert (
        client.post(
            "/api/v1/submissions", headers=headers, json={**command, "code": "changed"}
        ).status_code
        == 409
    )
    second = send(client, headers, "/submissions", submission("作品 B", 2))
    assert second["status"] == "SUCCEEDED"
    core = client.app.state.core
    first_file = (
        core.settings.data_dir / f"submissions/{info['id']}/{command['submission_id']}/index.html"
    )
    assert first_file.read_text(encoding="utf-8") == "作品 A"
    export = tmp_path / "session.zip"
    export_session(core, info["id"], export)
    report = validate_export(export)
    assert (
        report["valid"]
        and report["counts"]["submissions"] == 2
        and report["final_submission_id"] == second["id"]
    )
    archive = tmp_path / "backup.zip"
    backup(core, archive)
    target = tmp_path / "restored"
    assert restore(archive, target)["valid"]
    with sqlite3.connect(target / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 2
    assert (target / first_file.relative_to(core.settings.data_dir)).read_text(
        encoding="utf-8"
    ) == "作品 A"
    with pytest.raises(ValueError):
        restore(archive, target)


def test_write_failure_is_not_success_and_preview_not_replaced(client, monkeypatch):
    _, headers = enter(client)
    import app.services.submissions as module

    def fail(*args):
        raise OSError("injected disk failure")

    monkeypatch.setattr(module, "atomic_write", fail)
    result = send(client, headers, "/submissions", submission())
    assert result["status"] == "FAILED"
    assert not client.get("/api/v1/workbench/state", headers=headers).json()["code"]["content"]
    import app.services.preview as preview

    monkeypatch.setattr(preview, "atomic_write", fail)
    response = client.post(
        "/api/v1/workbench/preview/run",
        headers=headers,
        json={**occurrence(), "content": "A", "revision": 1, "run_id": identifier()},
    )
    assert response.status_code == 503 and "url" not in response.json()


def test_pending_submission_restart_recovery(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:
        info, headers = enter(client)
        service = client.app.state.submissions
        command = submission()
        monkeypatch.setattr(service, "finish", lambda record: record)
        assert send(client, headers, "/submissions", command)["status"] == "PENDING"
    with TestClient(create_app(settings)) as client:
        state = client.get("/api/v1/workbench/state", headers=headers).json()
        assert state["submissions"][0]["status"] == "SUCCEEDED"
        assert state["code"]["content"] == command["code"]


def test_concurrent_event_batches(client):
    info, headers = enter(client)
    events = [event(client_sequence_no=i + 1) for i in range(20)]

    def submit(row):
        return send(client, headers, "/events/batch", {"session_id": info["id"], "events": [row]})

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(r["results"][0]["status"] == "accepted" for r in pool.map(submit, events))
    with client.app.state.core.db.read() as conn:
        rows = conn.execute(
            "SELECT sequence_no FROM events WHERE session_id=? ORDER BY sequence_no", (info["id"],)
        ).fetchall()
    assert [r[0] for r in rows] == list(range(1, 23))


def test_three_ai_sessions_queue_with_two_global_slots(settings):
    import asyncio
    import threading

    class ControlledProvider:
        model = "controlled-test"

        def __init__(self):
            self.active = 0
            self.peak = 0
            self.release = threading.Event()
            self.inputs = []

        async def stream_chat(self, messages, attachments, request_id):
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.inputs.append(messages[-1]["content"])
            try:
                yield "第一段"
                while not self.release.is_set():
                    await asyncio.sleep(0.005)
                yield "完成"
            finally:
                self.active -= 1

    provider = ControlledProvider()
    with TestClient(create_app(settings, provider=provider)) as client:
        clients = [enter(client, seat) for seat in ("01", "02", "03")]
        requests = [
            send(client, headers, "/ai/requests", ai_command(message_text=f"seat-{index}"))
            for index, (_, headers) in enumerate(clients)
        ]
        assert (
            client.post("/api/v1/ai/requests", headers=clients[0][1], json=ai_command()).status_code
            == 409
        )
        states = [
            client.app.state.ai.read(info["id"], request["id"])[0]["status"]
            for (info, _), request in zip(clients, requests)
        ]
        assert states.count("STREAMING") == 2 and states.count("QUEUED") == 1
        provider.release.set()
        for (_, headers), request in zip(clients, requests):
            result = finish_ai(client, headers, request["id"])
            assert result["response"]["response_text"] == "第一段完成"
        assert provider.peak == 2 and set(x.split("\n当前代码：")[0] for x in provider.inputs) == {
            "seat-0",
            "seat-1",
            "seat-2",
        }


def test_code_revision_database_busy_and_backup_lock(client):
    from app.services.locking import data_lock

    _, headers = enter(client)
    # A real second process lock is exercised by maintenance acquisition in the same OS.
    with pytest.raises((RuntimeError, OSError)):
        with data_lock(client.app.state.core.settings.data_dir):
            pass
    db = client.app.state.core.db
    with db.transaction() as conn:
        conn.execute("UPDATE sessions SET last_seen_at=last_seen_at")
        with db.read() as second:
            second.execute("PRAGMA busy_timeout=1")
            with pytest.raises(sqlite3.OperationalError):
                second.execute("BEGIN IMMEDIATE")
    assert (
        client.put(
            "/api/v1/workbench/code", headers=headers, json={"content": "after-lock", "revision": 1}
        ).status_code
        == 200
    )


def test_idempotency_header_matches_business_identifier(client):
    _, headers = enter(client)
    command = submission()
    keyed = {**headers, "Idempotency-Key": command["submission_id"]}
    first = client.post("/api/v1/submissions", headers=keyed, json=command)
    second = client.post("/api/v1/submissions", headers=keyed, json=command)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    mismatch = client.post(
        "/api/v1/submissions", headers={**headers, "Idempotency-Key": "different"}, json=command
    )
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "IDEMPOTENCY_KEY_MISMATCH"
