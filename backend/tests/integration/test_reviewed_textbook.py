import json
import zipfile
from dataclasses import replace

import pytest
from app.repositories.database import encode
from app.services.attachments import parse_file
from app.services.exporting import backup, export_session, restore, validate_export
from app.services.files import resolve_ref
from app.settings import ROOT

from backend.tests.conftest import enter, occurrence
from backend.tests.integration.test_workflow import ai_command, finish_ai, identifier, send


def textbook_task():
    return json.loads((ROOT / "config/task-templates/unit6.json").read_text(encoding="utf-8"))


def test_real_textbook_over_attachment_limit_uses_reviewed_pages_and_freezes(client, tmp_path):
    c = client.app.state.core
    task = textbook_task()
    raw = (ROOT / "config/resources" / task["resources"][0]["file"]).read_bytes()
    assert len(raw) > c.settings.attachment_max
    with pytest.raises(ValueError, match="大小上限"):
        parse_file(task["resources"][0]["file"], "application/pdf", raw, c.settings)
    c.collection.publish(task)
    # Assign this real resource to a test session without publishing a formal study.
    info, h = enter(client)
    with c.db.transaction() as conn:
        snapshot = json.loads(c.db.session(conn, info["id"])["task_json"])
        snapshot["resources"] = task["resources"]
        conn.execute("UPDATE sessions SET task_json=? WHERE id=?", (encode(snapshot), info["id"]))
    resource = client.get("/api/v1/tasks/task-test/resources", headers=h).json()["resources"][0]
    assert resource["page_count"] == 27 and resource["ai_input_status"] == "ready"
    assert all(p["ai_input_status"] == "ready" for p in resource["pages"])
    assert resource["pages"][6]["printed_page"] == 98
    assert "(6) ________" in resource["pages"][6]["text"]
    assert "It looks like..." in resource["pages"][8]["text"]
    assert "Bingiie" not in resource["pages"][11]["text"]
    assert "Animals can ________ us." in resource["pages"][17]["text"]
    assert "<img" not in resource["extracted_text"]
    did = identifier()
    refs = []
    for page in (7, 9, 27):
        refs.append(
            send(
                client,
                h,
                f"/drafts/{did}/references",
                {
                    **occurrence(),
                    "reference_id": identifier(),
                    "draft_revision": 0,
                    "resource_id": resource["id"],
                    "resource_version": resource["version"],
                    "page": page,
                    "fragment": None,
                },
            )
        )
    request = send(
        client,
        h,
        "/ai/requests",
        ai_command(
            draft_id=did,
            reference_ids=[r["reference_id"] for r in refs],
        ),
    )
    frozen = finish_ai(client, h, request["id"])["request"]
    assert [s["page"] for s in frozen["input_sources"]] == [7, 9, 27]
    for ref in refs:
        assert ref["extracted_text"] in frozen["model_user_text"]
    assert resource["pages"][22]["text"] not in frozen["model_user_text"]
    export = tmp_path / "textbook.zip"
    export_session(c, info["id"], export)
    assert validate_export(export)["valid"]
    with zipfile.ZipFile(export) as archive:
        for key in ("storage_ref", "raw_ocr_ref", "reviewed_text_ref", "page_content_ref"):
            assert any(n.endswith(resource[key]) for n in archive.namelist())
    target = tmp_path / "restored"
    package = tmp_path / "backup.zip"
    backup(c, package)
    restore(package, target)
    for key in ("raw_ocr_ref", "reviewed_text_ref", "page_content_ref"):
        assert (
            resolve_ref(target, resource[key]).read_bytes()
            == resolve_ref(c.settings.data_dir, resource[key]).read_bytes()
        )
    # Frozen version cannot silently change after publication.
    c.collection.publish(task)
    changed = json.loads(json.dumps(task))
    changed["resources"][0]["title"] = "Changed"
    with pytest.raises(ValueError, match="新的 version"):
        c.collection.publish(changed)


@pytest.mark.parametrize("mutation", ["hash", "pages", "order", "mapping", "empty"])
def test_reviewed_text_must_match_pdf_page_order_and_mapping(
    client, tmp_path, monkeypatch, mutation
):
    import app.services.collection as module

    task = textbook_task()
    item = task["resources"][0]
    original = ROOT / "config/resources"
    folder = tmp_path / "config/resources"
    folder.mkdir(parents=True)
    (folder / item["file"]).write_bytes((original / item["file"]).read_bytes())
    reviewed = json.loads((original / item["reviewed_text_file"]).read_text(encoding="utf-8"))
    if mutation == "hash":
        reviewed["source_pdf_sha256"] = "wrong"
    elif mutation == "pages":
        reviewed["pages"].pop()
    elif mutation == "order":
        reviewed["pages"][0]["page"] = 2
    elif mutation == "mapping":
        reviewed["pages"][2]["printed_page"] = 95
    else:
        reviewed["pages"][0]["text"] = " "
    (folder / item["reviewed_text_file"]).write_text(encode(reviewed), encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="校对文字"):
        client.app.state.core.collection.publish(task)


def test_resource_limit_is_separate_and_fails_before_publication(client):
    c = client.app.state.core
    c.settings = replace(c.settings, resource_max=1024)
    with pytest.raises(ValueError, match="RESOURCE_MAX_BYTES"):
        c.collection.publish(textbook_task())
    with c.db.read() as conn:
        assert not conn.execute("SELECT 1 FROM resources WHERE id='unit6-textbook'").fetchone()


def test_pdf_extraction_over_attachment_limit_without_sidecar(client):
    task = textbook_task()
    item = task["resources"][0]
    item.pop("reviewed_text_file")
    item["version"] = "raw-ocr-test"
    c = client.app.state.core
    c.collection.publish(task)
    with c.db.read() as conn:
        resource = json.loads(
            conn.execute(
                "SELECT body FROM resources WHERE id=? AND version=?", (item["id"], item["version"])
            ).fetchone()[0]
        )
    assert resource["ai_input_status"] == "ready"
    assert len(resource["pages"]) == 27
    assert c.settings.attachment_max == 10485760
