import csv
import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from io import StringIO
from pathlib import Path

from app.repositories.database import TABLES, encode
from app.services.files import atomic_write, digest, resolve_ref


def apply_changes_utf16(text, changes):
    raw = text.encode("utf-16-le", errors="surrogatepass")
    for change in changes:
        start, end = (change["edit_range"][key] * 2 for key in ("start", "end"))
        deleted = change["deleted_text"].encode("utf-16-le", errors="surrogatepass")
        if raw[start:end] != deleted or start > len(raw) or end > len(raw):
            raise ValueError("编辑差分与源文本不一致")
        raw = (
            raw[:start]
            + change["inserted_text"].encode("utf-16-le", errors="surrogatepass")
            + raw[end:]
        )
    return raw.decode("utf-16-le", errors="surrogatepass")


def check_edit_replay(events, records):
    count = 0
    for name, table, prefix in (
        ("code_edited", "code_revisions", "code"),
        ("planner_edited", "planner_revisions", "plan"),
    ):
        versions = {0: "", **{r["revision"]: r["content"] for r in records[table]}}
        for event in events:
            if event["event_name"] != name:
                continue
            payload = event["payload"]
            start, end = payload[f"base_{prefix}_revision"], payload[f"{prefix}_revision"]
            if start not in versions or end not in versions:
                raise ValueError(f"{name} 引用版本缺失，请先补传草稿：{start} → {end}")
            replayed = apply_changes_utf16(versions[start], payload["edit_changes"])
            if (
                replayed != versions[end]
                or len(replayed.encode("utf-16-le")) // 2 != payload["content_length_after"]
            ):
                raise ValueError(f"{name} 差分重放与版本 {end} 不一致")
            count += 1
    return count


def export_session(core, sid, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("输出文件已存在，请使用新的导出文件名")
    with core.db.read() as conn:
        conn.execute("BEGIN")
        session = core.db.session(conn, sid)
        if not session:
            raise ValueError("会话不存在")
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY sequence_no", (sid,)
            )
        ]
        records = {table: core.db.all(conn, table, sid) for table in sorted(TABLES)}
    for event in events:
        event["payload"] = json.loads(event.pop("payload_json"))
        event.pop("fingerprint")
    files = {
        "session.json": encode(session).encode(),
        "task.json": session["task_json"].encode(),
        "events.jsonl": ("\n".join(encode(e) for e in events) + "\n").encode(),
    }
    text = StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(events[0]) if events else ["event_id"])
    writer.writeheader()
    writer.writerows([{**row, "payload": encode(row["payload"])} for row in events])
    files["events.csv"] = text.getvalue().encode("utf-8-sig")
    refs = set()
    for table, rows in records.items():
        files[f"records/{table}.json"] = encode(rows).encode()
        for row in rows:
            refs.update(
                value
                for key, value in row.items()
                if key
                in {
                    "content_ref",
                    "storage_ref",
                    "code_ref",
                    "plan_ref",
                    "manifest_ref",
                    "checksums_ref",
                }
                and value
            )
    ended_ref = f"ended/{sid}.json"
    if (core.settings.data_dir / ended_ref).exists():
        refs.add(ended_ref)
    for ref in sorted(refs):
        files[f"files/{ref}"] = resolve_ref(core.settings.data_dir, ref).read_bytes()
    final = next((s for s in reversed(records["submissions"]) if s["status"] == "SUCCEEDED"), None)
    report = {
        "event_count": len(events),
        "unique_event_ids": len({e["event_id"] for e in events}),
        "sequence_contiguous": [e["sequence_no"] for e in events]
        == list(range(1, len(events) + 1)),
        "reference_count": len(refs),
        "final_submission_id": final["id"] if final else None,
        "has_submission": final is not None,
        "counts": {table: len(rows) for table, rows in records.items()},
    }
    files["quality-report.json"] = encode(report).encode()
    manifest = {
        "format": "teaching-workbench-export-v1.1",
        "session_id": sid,
        "created_at": core.now(),
        "sequence_semantics": "server persistence order; client_sequence_no retains browser order",
        "edit_offset_encoding": "UTF-16 code units",
        "files": {key: digest(raw) for key, raw in files.items()},
        "references": sorted(refs),
        "quality": report,
    }
    files["manifest.json"] = encode(manifest).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        temp_zip = Path(temp) / "export.zip"
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        validate_export(temp_zip)
        atomic_write(output, temp_zip.read_bytes())
    return manifest


def validate_export(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, sha in manifest["files"].items():
            if digest(archive.read(name)) != sha:
                raise ValueError(f"文件校验失败：{name}")
        events = [
            json.loads(line) for line in archive.read("events.jsonl").decode().splitlines() if line
        ]
        if len(events) != manifest["quality"]["event_count"] or len(
            {e["event_id"] for e in events}
        ) != len(events):
            raise ValueError("事件数量或幂等性校验失败")
        if [e["sequence_no"] for e in events] != list(range(1, len(events) + 1)):
            raise ValueError("服务器入库序号不连续")
        if any(e["session_id"] != manifest["session_id"] for e in events):
            raise ValueError("会话隔离校验失败")
        for ref in manifest["references"]:
            if f"files/{ref}" not in manifest["files"]:
                raise ValueError("缺少文件引用")
        records = {table: json.loads(archive.read(f"records/{table}.json")) for table in TABLES}
        ids = {table: {r["id"] for r in rows} for table, rows in records.items()}
        mappings = {
            "request_id": "ai_requests",
            "response_id": "ai_responses",
            "run_id": "preview_runs",
            "attachment_id": "attachments",
            "submission_id": "submissions",
            "snapshot_id": "snapshots",
            "error_id": "preview_logs",
        }
        for event in events:
            for key, table in mappings.items():
                value = event["payload"].get(key)
                # Confirmed/failed attempts may not have produced a successful snapshot.
                if key == "snapshot_id" and event["event_name"] == "submit_confirmed":
                    continue
                if value and value not in ids[table]:
                    raise ValueError(f"{event['event_name']} 缺少 {key} 引用")
        for sub in records["submissions"]:
            if sub["status"] == "SUCCEEDED":
                snap = next(r for r in records["snapshots"] if r["id"] == sub["snapshot_id"])
                for key, field in (("code_ref", "code"), ("plan_ref", "plan")):
                    if archive.read("files/" + snap[key]).decode() != sub["command"][field]:
                        raise ValueError("提交文本与快照不同")
        verified_edits = check_edit_replay(events, records)
        return {"valid": True, "verified_edit_events": verified_edits, **manifest["quality"]}


def backup(core, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("备份文件已存在")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        root = Path(temp)
        # Caller stops API before backup, so DB and referenced files share one stable state.
        with core.db.read() as source, closing(sqlite3.connect(root / "app.db")) as target:
            source.backup(target)
        files = {"app.db": (root / "app.db").read_bytes()}
        for folder in (
            "attachments",
            "code-snapshots",
            "planner-snapshots",
            "previews",
            "submissions",
            "ended",
        ):
            base = core.settings.data_dir / folder
            if base.exists():
                for path in base.rglob("*"):
                    if path.is_file() and not any(p.startswith(".pending-") for p in path.parts):
                        files[path.relative_to(core.settings.data_dir).as_posix()] = (
                            path.read_bytes()
                        )
        token_file = core.settings.data_dir / "seat-tokens.json"
        if token_file.exists():
            files["seat-tokens.json"] = token_file.read_bytes()
        manifest = {
            "format": "teaching-workbench-backup-v1.1",
            "created_at": core.now(),
            "files": {name: digest(raw) for name, raw in files.items()},
        }
        archive_path = root / "backup.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
            archive.writestr("backup-manifest.json", encode(manifest))
        atomic_write(output, archive_path.read_bytes())
    return manifest


def restore(input_path, target):
    target = Path(target).resolve()
    if target.exists():
        raise ValueError("恢复目标必须是不存在的新目录，不能覆盖原数据")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        root = Path(staging) / "restored"
        root.mkdir()
        with zipfile.ZipFile(input_path) as archive:
            manifest = json.loads(archive.read("backup-manifest.json"))
            for name, sha in manifest["files"].items():
                path = resolve_ref(root, name)
                raw = archive.read(name)
                if digest(raw) != sha:
                    raise ValueError(f"备份文件损坏：{name}")
                atomic_write(path, raw)
        with closing(sqlite3.connect(root / "app.db")) as conn:
            if (
                conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or conn.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("恢复数据库完整性检查失败")
            for table in TABLES:
                for (body,) in conn.execute(f"SELECT body FROM {table}"):
                    for key, value in json.loads(body).items():
                        if (
                            key
                            in {
                                "content_ref",
                                "storage_ref",
                                "code_ref",
                                "plan_ref",
                                "manifest_ref",
                                "checksums_ref",
                            }
                            and value
                            and not resolve_ref(root, value).is_file()
                        ):
                            raise ValueError("恢复后缺少引用文件")
        shutil.move(str(root), str(target))
    return {"valid": True, "target": str(target), "files": len(manifest["files"])}
