import csv
import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from io import StringIO
from pathlib import Path

from app.domain.events import LEGACY_VERSION, validate_payload
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


def check_replay_v13(events, records):
    """Rebuild transaction order, using summaries once; verify delta references separately."""
    count = 0
    deltas = {
        e["payload"]["delta_id"]: e["payload"]
        for e in events
        if e["event_name"] == "code_edit_delta"
    }
    for kind, table in (("code", "code_revisions"), ("plan", "planner_revisions")):
        versions = {0: "", **{r["revision"]: r["content"] for r in records[table]}}
        selected = [
            e
            for e in events
            if e["event_name"]
            in (
                {"code_edited", "code_pasted", "ai_proposal_applied"}
                if kind == "code"
                else {"planner_edited"}
            )
        ]
        for e in sorted(
            selected,
            key=lambda e: (e["payload"][f"base_{kind}_revision"], e["payload"][f"{kind}_revision"]),
        ):
            p = e["payload"]
            base = p[f"base_{kind}_revision"]
            end = p[f"{kind}_revision"]
            if base not in versions:
                raise ValueError(f"缺少 {kind} 基线版本 {base}")
            if e["event_name"] == "code_pasted":
                raw = versions[base].encode("utf-16-le")
                r = p["edit_range"]
                if r["end"] * 2 > len(raw):
                    raise ValueError("粘贴范围超出基线")
                rebuilt = (
                    raw[: r["start"] * 2]
                    + p["pasted_text"].encode("utf-16-le")
                    + raw[r["end"] * 2 :]
                ).decode("utf-16-le")
            else:
                changes = p["edit_changes"]
                if (
                    not changes
                    or changes[0]["base_revision"] != base
                    or changes[-1]["result_revision"] != end
                ):
                    raise ValueError("编辑事务版本边界不一致")
                rebuilt = apply_changes_utf16(versions[base], changes)
                if e["event_name"] == "code_edited":
                    try:
                        detail = [c for did in p["delta_ids"] for c in deltas[did]["changes"]]
                    except KeyError as exc:
                        raise ValueError("缺少代码明细批次") from exc
                    if detail != changes:
                        raise ValueError("代码汇总和明细不一致")
                if (
                    "content_length_after" in p
                    and len(rebuilt.encode("utf-16-le")) // 2 != p["content_length_after"]
                ):
                    raise ValueError("编辑后长度不一致")
            if end in versions and versions[end] != rebuilt:
                raise ValueError(f"{kind} 差分与版本 {end} 不一致")
            versions[end] = rebuilt
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
        core.research_access.require(session["participant_id"])
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY sequence_no", (sid,)
            )
        ]
        records = {table: core.db.all(conn, table, sid) for table in sorted(TABLES)}
        transports = {
            r["event_id"]: dict(r)
            for r in conn.execute(
                "SELECT t.* FROM event_transport t JOIN events e ON e.event_id=t.event_id WHERE e.session_id=?",
                (sid,),
            )
        }
        calibrations = [
            json.loads(r[0])
            for r in conn.execute("SELECT body FROM clock_calibrations WHERE session_id=?", (sid,))
        ]
        resources = [
            json.loads(
                conn.execute(
                    "SELECT body FROM resources WHERE id=? AND version=?", (r["id"], r["version"])
                ).fetchone()[0]
            )
            for r in json.loads(session["task_json"]).get("resources", [])
        ]
        capture_records = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM capture_records WHERE participant_id=?", (session["participant_id"],)
            )
        ]
        capture_events = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT body FROM capture_events WHERE participant_id=? ORDER BY recording_id,capture_sequence_no",
                (session["participant_id"],),
            )
        ]
        for marker in capture_events:
            cid = marker["payload"].get("clock_calibration_id")
            if cid and not any(
                r.get("id", r.get("clock_calibration_id")) == cid for r in calibrations
            ):
                row = conn.execute(
                    "SELECT body FROM clock_calibrations WHERE id=?", (cid,)
                ).fetchone()
                if row:
                    calibrations.append(json.loads(row[0]))
        recording_sessions = [
            dict(r)
            for r in conn.execute("SELECT * FROM recording_sessions WHERE session_id=?", (sid,))
        ]
    for event in events:
        event["payload"] = json.loads(event.pop("payload_json"))
        event.pop("fingerprint")
        t = transports.get(event["event_id"])
        event["schema_version"] = (
            t["schema_version"] if t else session.get("schema_version", LEGACY_VERSION)
        )
        event.update(
            json.loads(t["body"])
            if t
            else {
                "producer_id": None,
                "producer_seq": None,
                "raw_time": None,
                "monotonic_ms": None,
                "clock_calibration_id": None,
                "time_source": "unknown_legacy",
                "action_id": None,
                "causal_parent_ids": [],
            }
        )
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

    def csv_bytes(rows, default_fields):
        output = StringIO(newline="")
        fields = list(dict.fromkeys(k for row in rows for k in row)) or default_fields
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [
                {k: encode(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
                for row in rows
            ]
        )
        return output.getvalue().encode("utf-8-sig")

    groups = {
        kind: [
            json.loads(r["body"])
            for r in capture_records
            if r["kind"] == kind
            and (kind in {"media", "anchor"} or json.loads(r["body"]).get("session_id") == sid)
        ]
        for kind in (
            "media",
            "anchor",
            "annotations",
            "artifact_ratings",
            "retrospective",
            "conditions",
            "field_records",
            "research_files",
        )
    }
    files["capture_events.jsonl"] = ("\n".join(encode(e) for e in capture_events) + "\n").encode()
    files["clock_calibrations.json"] = encode(calibrations).encode()
    files["resources.json"] = encode(resources).encode()
    files["participant_sessions.csv"] = csv_bytes(
        [
            {
                "participant_id": session["participant_id"],
                "session_id": sid,
                "task_id": session["task_id"],
                "condition_id": json.loads(session["task_json"]).get("condition_id"),
                "seat_no": session["seat_no"],
                "task_version": session["task_version"],
            }
        ],
        [],
    )
    files["recording_sessions.csv"] = csv_bytes(
        recording_sessions, ["recording_id", "session_id", "video_start_ms", "video_end_ms"]
    )
    for name, rows in [
        ("media_manifest", groups["media"]),
        ("sync_anchors", groups["anchor"]),
        ("annotations", groups["annotations"]),
        ("artifact_ratings", groups["artifact_ratings"]),
        ("retrospective", groups["retrospective"]),
        ("conditions", groups["conditions"]),
        ("field_records", groups["field_records"]),
        ("research_files", groups["research_files"]),
    ]:
        files[name + ".csv"] = csv_bytes(rows, ["record_id"])
    refs = {
        r[k]
        for r in resources + groups["media"] + groups["research_files"]
        for k in (
            "storage_ref",
            "extracted_text_ref",
            "page_content_ref",
            "raw_ocr_ref",
            "reviewed_text_ref",
        )
        if r.get(k)
    }
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
                    "design_rationale_ref",
                    "manifest_ref",
                    "checksums_ref",
                    "proposal_content_ref",
                }
                and value
            )
    ended_ref = f"ended/{sid}.json"
    if (core.settings.data_dir / ended_ref).exists():
        refs.add(ended_ref)
    missing = []
    for ref in sorted(refs):
        path = resolve_ref(core.settings.data_dir, ref)
        if path.is_file():
            files[f"files/{ref}"] = path.read_bytes()
        else:
            missing.append(ref)
    final = max(
        (s for s in records["submissions"] if s["status"] == "SUCCEEDED"),
        key=lambda s: s.get("submission_no", 0),
        default=None,
    )
    media_by_id = {m["recording_id"]: m for m in groups["media"]}
    incomplete_recordings = []
    for link in recording_sessions:
        media = media_by_id.get(link["recording_id"], {})
        anchors = [
            a
            for a in groups["anchor"]
            if a["recording_id"] == link["recording_id"] and a.get("pts_verified")
        ]
        if not (
            media.get("archive_status") == "archived"
            and media.get("media_verified", False)
            and not media.get("known_gaps")
            and len({a["video_pts_ms"] for a in anchors}) >= 2
            and min(a["video_pts_ms"] for a in anchors) <= link["video_start_ms"]
            and max(a["video_pts_ms"] for a in anchors) >= link["video_end_ms"]
        ):
            incomplete_recordings.append(link["recording_id"])
    report = {
        "schema_version": session["schema_version"],
        "missing_files": missing,
        "recording_bound": bool(recording_sessions),
        "multimodal_complete": bool(recording_sessions)
        and not missing
        and not incomplete_recordings,
        "incomplete_bound_recordings": sorted(set(incomplete_recordings)),
        "missing_media": [
            r["recording_id"] for r in groups["media"] if r.get("archive_status") != "archived"
        ],
        "unresolved_attempts": {
            t: [
                r["id"] for r in records[t] if r.get("status") in {"PENDING", "QUEUED", "STREAMING"}
            ]
            for t in ("preview_runs", "submissions", "ai_requests", "proposal_applications")
        },
        "fallback_source": None if final else "autosave_fallback",
        "order_version": None,
        "missing_causal_parents": sorted(
            {
                p
                for e in events
                for p in e.get("causal_parent_ids", [])
                if p not in {r["event_id"] for r in events}
            }
        ),
        "event_count": len(events),
        "unique_event_ids": len({e["event_id"] for e in events}),
        "sequence_contiguous": [e["sequence_no"] for e in events]
        == list(range(1, len(events) + 1)),
        "reference_count": len(refs),
        "final_submission_id": final["id"] if final else None,
        "has_submission": final is not None,
        "missing_research_materials": [
            kind
            for kind in (
                "conditions",
                "field_records",
                "annotations",
                "artifact_ratings",
                "retrospective",
            )
            if not groups[kind]
        ],
        "design_rationale_status": "provided"
        if final and final["command"].get("design_rationale")
        else "missing",
        "counts": {table: len(rows) for table, rows in records.items()},
    }
    files["quality-report.json"] = files["quality.json"] = encode(report).encode()
    manifest = {
        "format": "teaching-workbench-export-v1.3",
        "schema_version": session["schema_version"],
        "order_version": None,
        "session_id": sid,
        "created_at": core.now(),
        "sequence_semantics": "server persistence order; client_sequence_no retains browser order",
        "edit_offset_encoding": "UTF-16 code units",
        "contract_revision": "2026-10-12",
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
            if f"files/{ref}" not in manifest["files"] and ref not in manifest["quality"].get(
                "missing_files", []
            ):
                raise ValueError("缺少文件引用")
        records = {
            table: json.loads(archive.read(f"records/{table}.json"))
            if f"records/{table}.json" in archive.namelist()
            else []
            for table in TABLES
        }
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
            validate_payload(
                event["event_name"],
                event["payload"],
                event.get("schema_version", LEGACY_VERSION),
                historical=True,
            )
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
                if sub["command"].get("design_rationale") is not None:
                    if (
                        archive.read("files/" + snap["design_rationale_ref"]).decode()
                        != sub["command"]["design_rationale"]
                    ):
                        raise ValueError("提交设计说明与快照不同")
        verified_edits = (
            check_edit_replay(events, records)
            if all(e.get("schema_version", LEGACY_VERSION) == LEGACY_VERSION for e in events)
            else check_replay_v13(events, records)
        )
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
        files["research-restrictions.json"] = encode(core.research_access.records()).encode()
        for folder in (
            "attachments",
            "code-snapshots",
            "planner-snapshots",
            "previews",
            "submissions",
            "ended",
            "resources",
            "proposals",
            "capture",
            "research",
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
            "format": "teaching-workbench-backup-v1.3",
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


def restore(input_path, target, restrictions_path=None):
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
        restrictions_path = (
            Path(restrictions_path)
            if restrictions_path
            else target.parent / "research-restrictions.json"
        )
        records = (
            json.loads((root / "research-restrictions.json").read_text(encoding="utf-8"))
            if (root / "research-restrictions.json").exists()
            else {}
        )
        if restrictions_path.exists():
            records.update(json.loads(restrictions_path.read_text(encoding="utf-8")))
        if records:
            atomic_write(restrictions_path, encode(records))
        with closing(sqlite3.connect(root / "app.db")) as conn:
            if (
                conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or conn.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("恢复数据库完整性检查失败")
            existing_tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table in (TABLES | {"resources", "capture_records"}) & existing_tables:
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
                                "proposal_content_ref",
                                "extracted_text_ref",
                                "page_content_ref",
                                "raw_ocr_ref",
                                "reviewed_text_ref",
                                "design_rationale_ref",
                            }
                            and value
                            and not resolve_ref(root, value).is_file()
                        ):
                            raise ValueError("恢复后缺少引用文件")
        shutil.move(str(root), str(target))
    return {"valid": True, "target": str(target), "files": len(manifest["files"])}
