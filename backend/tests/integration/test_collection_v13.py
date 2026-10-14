import json
import sqlite3
import zipfile
from datetime import timedelta

import pytest
from app.domain.commands import Application, Decision
from app.services.capture import CaptureService
from app.services.core import Core
from app.services.exporting import export_session, validate_export
from app.settings import ROOT

from backend.tests.conftest import enter, occurrence
from backend.tests.integration.test_workflow import ai_command, event, finish_ai, identifier, send


def prepare(client, seat="01"):
    entry = client.post(
        "/api/v1/entry/bootstrap", json={"seat": seat, "token": client.app.state.core.seed()[seat]}
    ).json()
    headers = {"Authorization": "Bearer " + entry["token"], "X-Writer-Id": "writer-" + seat}
    info = send(
        client,
        headers,
        "/session/bootstrap",
        {"task_id": "task-test", "writer_id": headers["X-Writer-Id"]},
    )
    headers["Authorization"] = "Bearer " + info["token"]
    return info, headers


def test_preparation_gate_frozen_answers_and_identity(client):
    info, h = prepare(client)
    assert info["status"] == "PREPARING" and info["started_at"] is None
    task = client.get("/api/v1/tasks/task-test", headers=h).json()
    assert "description" not in task and len(task["prerequisite"]["questions"]) == 5
    assert client.get("/api/v1/tasks/task-test/resources", headers=h).status_code == 409
    assert client.post("/api/v1/ai/requests", headers=h, json=ai_command()).status_code == 409
    assert client.post("/api/v1/session/start", headers=h, json=occurrence()).status_code == 409
    answers = {
        **occurrence(),
        "version": task["prerequisite"]["version"],
        "responses": [
            {"question_id": q["id"], "answer_value": q["options"][0]["value"]}
            for q in task["prerequisite"]["questions"]
        ],
    }
    assert (
        client.post(
            "/api/v1/session/prerequisite",
            headers=h,
            json={**answers, "responses": answers["responses"][:-1]},
        ).status_code
        == 400
    )
    send(client, h, "/session/prerequisite", answers)
    send(client, h, "/session/prerequisite", answers)
    changed = json.loads(json.dumps(answers))
    changed["responses"][0]["answer_value"] = 1
    assert client.post("/api/v1/session/prerequisite", headers=h, json=changed).status_code == 409
    start = occurrence()
    active = send(client, h, "/session/start", start)
    send(client, h, "/session/start", start)
    with client.app.state.core.db.read() as conn:
        assert [
            r[0]
            for r in conn.execute(
                "SELECT event_name FROM events WHERE session_id=? ORDER BY sequence_no",
                (info["id"],),
            )
        ] == ["task_prerequisite_completed", "task_started"]
    assert active["started_at"] == start["occurred_at"]
    send(client, h, "/session/end", occurrence())
    new, _ = prepare(client)
    assert new["participant_id"] == info["participant_id"] and new["id"] != info["id"]


def test_detach_refresh_bfcache_expiry_and_writer_lease(client):
    info, h = enter(client)
    c = client.app.state.core
    assert (
        client.post("/api/v1/session/detach", headers=h, json={"persisted": False}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/session/heartbeat", headers={**h, "X-Writer-Id": "other"}).status_code
        == 409
    )
    instant = c.clock()
    c.clock = lambda: instant
    send(client, h, "/session/detach", {**occurrence(), "occurred_at": c.now(), "persisted": False})
    instant += timedelta(seconds=10)
    assert send(client, h, "/session/heartbeat", None)["status"] == "ACTIVE"
    send(client, h, "/session/detach", {**occurrence(), "occurred_at": c.now(), "persisted": True})
    instant += timedelta(seconds=20)
    c.expire()
    with c.db.read() as conn:
        assert c.db.session(conn, info["id"])["status"] == "ENDING"
        assert any(
            r["kind"] == "detach_cancelled" for r in c.db.all(conn, "session_technical", info["id"])
        )
    send(client, h, "/session/heartbeat", None)
    send(client, h, "/session/detach", {**occurrence(), "occurred_at": c.now(), "persisted": False})
    instant += timedelta(seconds=16)
    c.expire()
    with c.db.read() as conn:
        assert c.db.session(conn, info["id"])["status"] == "ENDED"


def test_ai_uses_click_time_code_version_after_later_autosave(client):
    info, h = enter(client)
    c = client.app.state.core
    c.save(info["id"], "code", "<p>sent version</p>", 1)
    c.save(info["id"], "code", "<p>later edit</p>", 2)
    cmd = ai_command(base_code_revision=1)
    request = send(client, h, "/ai/requests", cmd)
    assert request["base_code"] == "<p>sent version</p>"
    assert finish_ai(client, h, request["id"])["request"]["status"] == "SUCCEEDED"
    with c.db.read() as conn:
        assert c.latest(conn, info["id"], "code")["revision"] == 2


def test_draft_and_resource_reference_history(client):
    info, h = enter(client)
    _, other = enter(client, "02")
    did = identifier()
    resources = client.get("/api/v1/tasks/task-test/resources", headers=h).json()["resources"]
    resource = resources[0]
    cmd = {
        **occurrence(),
        "reference_id": identifier(),
        "resource_id": resource["id"],
        "resource_version": resource["version"],
        "draft_revision": 0,
        "page": 1,
        "fragment": None,
    }
    ref = send(client, h, f"/drafts/{did}/references", cmd)
    assert send(client, h, f"/drafts/{did}/references", cmd)["reference_id"] == ref["reference_id"]
    assert (
        client.request(
            "DELETE",
            f"/api/v1/drafts/{did}/references/{ref['reference_id']}",
            headers=other,
            json={**occurrence(), "draft_revision": 0},
        ).status_code
        == 404
    )
    for revision, content in [(2, "current"), (1, "previous")]:
        result = client.put(
            f"/api/v1/drafts/{did}",
            headers=h,
            json={
                "content": content,
                "revision": revision,
                "reference_ids": [ref["reference_id"]],
                "attachment_ids": [],
            },
        )
        assert result.status_code == 200, result.text
    state = client.get("/api/v1/workbench/state", headers=h).json()
    assert state["request_drafts"][0]["content"] == "current"
    assert len(state["draft_revisions"]) == 2
    request = send(
        client,
        h,
        "/ai/requests",
        ai_command(
            draft_id=did,
            draft_revision=2,
            message_text="current",
            reference_ids=[ref["reference_id"]],
        ),
    )
    assert finish_ai(client, h, request["id"])["request"]["status"] == "SUCCEEDED"
    result = client.request(
        "DELETE",
        f"/api/v1/drafts/{did}/references/{ref['reference_id']}",
        headers=h,
        json={**occurrence(), "draft_revision": 2},
    )
    assert result.status_code == 200
    with client.app.state.core.db.read() as conn:
        assert client.app.state.core.db.get(conn, "ai_requests", request["id"])["command"][
            "reference_ids"
        ] == [ref["reference_id"]]


def test_response_revision_evidence_proposal_conflicts_and_apply_once(client, tmp_path):
    info, h = enter(client)
    c = client.app.state.core
    request = send(client, h, "/ai/requests", ai_command())
    response = finish_ai(client, h, request["id"])["response"]
    state = client.get("/api/v1/workbench/state", headers=h).json()
    p = state["ai_proposals"][0]
    assert response["content_revision"] > 1
    bad = event(
        "ai_response_displayed",
        {
            "request_id": request["id"],
            "response_id": response["id"],
            "display_stage": "complete",
            "content_revision": 1,
            "rendered_range": {"start": 0, "end": 999999},
            "visible_ranges": [],
            "is_visible": False,
        },
        actor="system",
    )
    assert (
        send(client, h, "/events/batch", {"session_id": info["id"], "events": [bad]})["results"][0][
            "status"
        ]
        == "rejected"
    )
    shown = event(
        "ai_proposal_displayed",
        {
            "proposal_id": p["id"],
            "response_id": p["response_id"],
            "base_code_revision": p["base_code_revision"],
            "proposal_content_ref": p["proposal_content_ref"],
            "is_visible": True,
        },
        actor="system",
    )
    assert (
        send(client, h, "/events/batch", {"session_id": info["id"], "events": [shown]})["results"][
            0
        ]["status"]
        == "accepted"
    )
    decision = Decision(
        **occurrence(),
        decision="accept",
        display_event_id=shown["event_id"],
        decision_display_elapsed_ms=100,
    )
    proposals = client.app.state.ai.proposals
    proposals.decide(info["id"], p["id"], decision)
    assert client.get("/api/v1/workbench/state", headers=h).json()["code"]["content"] == ""
    command = Application(application_id=identifier(), current_revision=0)
    applied = proposals.apply(info["id"], p["id"], command)
    assert applied["status"] == "APPLIED"
    assert proposals.apply(info["id"], p["id"], command) == applied
    assert not client.get("/api/v1/workbench/state", headers=h).json()["preview_runs"]
    stale = proposals.apply(
        info["id"], p["id"], Application(application_id=identifier(), current_revision=1)
    )
    assert stale["status"] == "FAILED"
    assert client.get("/api/v1/workbench/state", headers=h).json()["code"]["content"] == p["code"]
    report = export_session(c, info["id"], tmp_path / "proposal.zip")
    assert report["quality"]["multimodal_complete"] is False
    assert validate_export(tmp_path / "proposal.zip")["verified_edit_events"] == 1


def test_capture_outside_active_missing_media_and_identity_validation(client, tmp_path):
    info, h = enter(client)
    other, _ = enter(client, "02")
    send(client, h, "/session/end", occurrence())
    service = CaptureService(client.app.state.core)
    rid = identifier()
    stamp = occurrence()
    marker = {
        **stamp,
        "participant_id": info["participant_id"],
        "payload": {
            "marker_id": identifier(),
            "recording_id": rid,
            "displayed_at": stamp["occurred_at"],
            "clock_calibration_id": None,
        },
    }
    assert service.marker(marker)["sequence_no"] is None
    assert service.marker(marker)["capture_sequence_no"] == 1
    media = {
        "recording_id": rid,
        "participant_id": info["participant_id"],
        "file_ref": "missing.webm",
        "segment": 1,
        "recording_started_at": stamp["occurred_at"],
        "recording_ended_at": stamp["occurred_at"],
        "duration_ms": 1000,
        "width": 1280,
        "height": 720,
        "frame_rate": 30,
        "known_gaps": [],
    }
    link = {"recording_id": rid, "session_id": info["id"], "video_start_ms": 0, "video_end_ms": 900}
    report = service.import_bundle(
        {"media_manifest": [media], "recording_sessions": [link]}, tmp_path
    )
    assert report["missing_media"] == [rid]
    with pytest.raises(ValueError, match="身份"):
        service.import_bundle(
            {"recording_sessions": [{**link, "session_id": other["id"]}]}, tmp_path
        )
    output = tmp_path / "capture.zip"
    export_session(client.app.state.core, info["id"], output)
    with zipfile.ZipFile(output) as z:
        assert json.loads(z.read("quality.json"))["multimodal_complete"] is False
        assert (
            json.loads(z.read("capture_events.jsonl"))["payload"]["marker_id"]
            == marker["payload"]["marker_id"]
        )


def test_v11_migration_retains_original_event_facts(settings, tmp_path):
    settings.database.parent.mkdir(parents=True)
    with sqlite3.connect(settings.database) as conn:
        conn.executescript(
            (ROOT / "backend/migrations/001_initial.sql").read_text(encoding="utf-8")
        )
        task = json.dumps(
            {"task_id": "old-task", "version": "old-v1", "title": "Old", "resources": []}
        )
        conn.execute(
            "INSERT INTO sessions VALUES('old','old-person','01','old-task','old-v1',?,'ENDED','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','2026-01-01T01:00:00Z',2)",
            (task,),
        )
        conn.execute(
            "INSERT INTO events VALUES('old-event','task_started','student','old','old-person','old-task','01','2026-01-01T00:00:00Z','2026-01-01T00:00:01Z',1,NULL,?, 'original-fingerprint')",
            (json.dumps({"entry_page": "task"}),),
        )
    core = Core(settings)
    core.initialize()
    output = tmp_path / "legacy.zip"
    export_session(core, "old", output)
    with zipfile.ZipFile(output) as z:
        e = json.loads(z.read("events.jsonl"))
        assert e["schema_version"] == "teaching-workbench-events-v1.1"
        assert e["actor"] == "student" and e["occurred_at"] == "2026-01-01T00:00:00Z"
        assert e["producer_id"] is None and e["time_source"] == "unknown_legacy"
    with core.db.transaction() as conn:
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET sequence_no=10 WHERE event_id='old-event'")
