import json
import zipfile

import pytest
from app.domain.events import validate_payload
from app.services.capture import CaptureService
from app.services.exporting import backup, export_session, restore, validate_export

from backend.tests.conftest import enter, occurrence
from backend.tests.integration.test_collection_v13 import prepare
from backend.tests.integration.test_workflow import ai_command, finish_ai, identifier, send


@pytest.mark.parametrize("refusals", [1, 5])
def test_explicit_refusal_is_not_missing_and_is_idempotent(client, refusals):
    info, headers = prepare(client)
    task = client.get("/api/v1/tasks/task-test", headers=headers).json()
    responses = [
        {"question_id": q["id"], "answer_value": None if i < refusals else q["options"][0]["value"]}
        for i, q in enumerate(task["prerequisite"]["questions"])
    ]
    command = {**occurrence(), "version": task["prerequisite"]["version"], "responses": responses}
    for wrong in (responses[:-1], [{"question_id": "Q1"}] + responses[1:]):
        assert client.post(
            "/api/v1/session/prerequisite", headers=headers, json={**command, "responses": wrong}
        ).status_code in {400, 422}
    send(client, headers, "/session/prerequisite", command)
    send(client, headers, "/session/prerequisite", command)
    send(client, headers, "/session/start", occurrence())
    with client.app.state.core.db.read() as conn:
        events = conn.execute(
            "SELECT event_name,payload_json FROM events WHERE session_id=? ORDER BY sequence_no",
            (info["id"],),
        ).fetchall()
    assert [r[0] for r in events] == ["task_prerequisite_completed", "task_started"]
    assert json.loads(events[0][1])["responses"] == responses


def test_page_references_freeze_only_selected_pages_and_export_sources(client, tmp_path):
    info, h = enter(client)
    resource = client.get("/api/v1/tasks/task-test/resources", headers=h).json()["resources"][0]
    assert resource["page_count"] == 3
    did = identifier()
    commands = [
        {
            **occurrence(),
            "reference_id": identifier(),
            "resource_id": resource["id"],
            "resource_version": resource["version"],
            "draft_revision": 0,
            "page": p,
            "fragment": None,
            "reference_purpose": "knowledge_point" if p == 1 else None,
            "reference_note": "select a point" if p == 1 else None,
        }
        for p in (1, 3)
    ]
    for bad in (None, 0, 4):
        assert (
            client.post(
                f"/api/v1/drafts/{did}/references", headers=h, json={**commands[0], "page": bad}
            ).status_code
            == 400
        )
    refs = [send(client, h, f"/drafts/{did}/references", c) for c in commands]
    assert refs[0]["printed_page"] == "T1"
    assert (
        client.post(
            f"/api/v1/drafts/{did}/references", headers=h, json={**commands[0], "page": 2}
        ).status_code
        == 409
    )
    request = send(
        client,
        h,
        "/ai/requests",
        ai_command(draft_id=did, reference_ids=[r["reference_id"] for r in refs]),
    )
    result = finish_ai(client, h, request["id"])
    frozen = result["request"]
    assert resource["pages"][0]["text"] in frozen["model_user_text"]
    assert resource["pages"][2]["text"] in frozen["model_user_text"]
    assert resource["pages"][1]["text"] not in frozen["model_user_text"]
    assert [s["page"] for s in frozen["input_sources"]] == [1, 3]
    export_session(client.app.state.core, info["id"], tmp_path / "pages.zip")
    assert validate_export(tmp_path / "pages.zip")["valid"]


def test_rationale_is_frozen_with_submission_and_restorable(client, tmp_path):
    info, h = enter(client)
    command = {
        **occurrence(),
        "submission_id": identifier(),
        "snapshot_id": identifier(),
        "code": "<p>A</p>",
        "plan": "",
        "code_revision": 1,
        "plan_revision": 0,
        "design_rationale": "A: teach animals",
    }
    sub = send(client, h, "/submissions", command)
    assert sub["status"] == "SUCCEEDED"
    client.put("/api/v1/workbench/code", headers=h, json={"content": "<p>B</p>", "revision": 2})
    assert (
        send(client, h, "/submissions", command)["command"]["design_rationale"]
        == "A: teach animals"
    )
    c = client.app.state.core
    export_session(c, info["id"], tmp_path / "rationale.zip")
    with zipfile.ZipFile(tmp_path / "rationale.zip") as z:
        snapshot = json.loads(z.read("records/snapshots.json"))[0]
        assert z.read("files/" + snapshot["design_rationale_ref"]).decode() == "A: teach animals"
    backup(c, tmp_path / "backup.zip")
    restore(tmp_path / "backup.zip", tmp_path / "restored")
    assert (
        tmp_path / "restored" / snapshot["design_rationale_ref"]
    ).read_text() == "A: teach animals"


def test_save_and_actual_load_are_distinct_and_reload_keeps_history(client):
    info, h = enter(client)
    run = send(
        client,
        h,
        "/workbench/preview/run",
        {**occurrence(), "run_id": identifier(), "content": "<button>Test</button>", "revision": 1},
    )
    path = "/workbench/preview/" + run["run_id"]
    assert client.get("/api/v1" + path, headers=h).json()["load_attempts"] == []
    load_id = identifier()
    send(
        client,
        h,
        path + "/load",
        {**occurrence(), "load_id": load_id, "state": "loading", "reason": "iframe_bound"},
    )
    send(
        client,
        h,
        path + "/interaction",
        {
            **occurrence(),
            "message_id": identifier(),
            "channel": run["channel"],
            "kind": "ready",
            "load_id": load_id,
        },
    )
    next_load = identifier()
    send(
        client,
        h,
        path + "/load",
        {**occurrence(), "load_id": next_load, "state": "loading", "reason": "reload"},
    )
    state = client.get("/api/v1" + path, headers=h).json()
    assert [r["state"] for r in state["load_attempts"]] == ["loaded", "loading"]
    send(
        client,
        h,
        path + "/load",
        {**occurrence(), "load_id": next_load, "state": "timeout", "reason": "handshake_timeout"},
    )
    assert client.get("/api/v1" + path, headers=h).json()["load_attempts"][-1]["state"] == "timeout"


def test_research_files_conditions_and_missing_materials_are_archived(client, tmp_path):
    info, h = enter(client)
    c = client.app.state.core
    (tmp_path / "notes.txt").write_text("teacher assistance recorded", encoding="utf-8")
    base = {"participant_id": info["participant_id"], "session_id": info["id"]}
    CaptureService(c).import_bundle(
        {
            "conditions": [
                {
                    **base,
                    "record_id": "conditions-1",
                    "condition_version": "v1",
                    "allowed_help": "teacher",
                }
            ],
            "research_files": [
                {
                    **base,
                    "record_id": "field-file-1",
                    "file_ref": "notes.txt",
                    "material_type": "field_records",
                }
            ],
        },
        tmp_path,
    )
    export_session(c, info["id"], tmp_path / "research.zip")
    with zipfile.ZipFile(tmp_path / "research.zip") as z:
        assert "conditions.csv" in z.namelist()
        assert "files/research/" + info["id"] + "/field-file-1/notes.txt" in z.namelist()
        quality = json.loads(z.read("quality.json"))
        assert "retrospective" in quality["missing_research_materials"]


def test_stopped_participant_cannot_upload_late_data_or_reappear_from_old_backup(client, tmp_path):
    info, h = enter(client)
    c = client.app.state.core
    backup(c, tmp_path / "before-stop.zip")
    c.research_access.stop(info["participant_id"], "participant request", "test-policy", True)
    assert client.get("/api/v1/workbench/state", headers=h).status_code == 403
    assert (
        client.put(
            "/api/v1/workbench/code", headers=h, json={"content": "late", "revision": 1}
        ).status_code
        == 403
    )
    with pytest.raises(Exception, match="采集已停止"):
        export_session(c, info["id"], tmp_path / "forbidden.zip")
    restore(tmp_path / "before-stop.zip", tmp_path / "restored", c.settings.restrictions_path)
    from app.services.core import Core
    from app.settings import Settings

    recovered = Core(
        Settings(
            data_dir=tmp_path / "restored",
            database=tmp_path / "restored/app.db",
            secret=c.settings.secret,
            research_restrictions=c.settings.restrictions_path,
        )
    )
    with pytest.raises(Exception, match="采集已停止"):
        export_session(recovered, info["id"], tmp_path / "also-forbidden.zip")


def test_historical_reference_contract_remains_readable_without_fabricated_fields():
    old = {
        "reference_id": "r",
        "resource_id": "book",
        "resource_version": "v1",
        "page": None,
        "fragment": None,
        "draft_id": "d",
        "draft_revision": 0,
    }
    assert validate_payload("resource_reference_added", old, historical=True) == old
    with pytest.raises(ValueError):
        validate_payload("resource_reference_added", old)
