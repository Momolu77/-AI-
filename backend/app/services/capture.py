"""Researcher-only local import of external recordings and post-task records."""

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from app.domain.events import SCHEMA_VERSION, Transport, parse_time, validate_payload
from app.repositories.database import encode
from app.services.files import atomic_write, digest


class CaptureService:
    def __init__(self, core, ffprobe=None):
        self.c = core
        self.ffprobe = ffprobe or shutil.which("ffprobe")

    def probe(self, path, interval=None):
        if not self.ffprobe:
            return None
        options = (
            ["-show_streams", "-show_format"]
            if interval is None
            else [
                "-read_intervals",
                f"{max(0, interval / 1000 - 1)}%+3",
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time",
            ]
        )
        result = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                *options,
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        return json.loads(result.stdout)

    def participant(self, conn, pid):
        self.c.research_access.require(pid)
        if not conn.execute("SELECT 1 FROM participants WHERE id=?", (pid,)).fetchone():
            raise ValueError("参与者不存在")

    def calibration(self, row):
        for key in ("client_send_time", "client_receive_time", "server_time"):
            parse_time(row[key])
        if row["round_trip_ms"] < 0 or row["uncertainty_ms"] < 0:
            raise ValueError("时钟误差无效")
        identifier = row.get("id") or row["clock_calibration_id"]
        with self.c.db.transaction() as conn:
            old = conn.execute(
                "SELECT body FROM clock_calibrations WHERE id=?", (identifier,)
            ).fetchone()
            if old and old[0] != encode(row):
                raise ValueError("校准编号冲突")
            conn.execute(
                "INSERT OR IGNORE INTO clock_calibrations VALUES(?,NULL,?)",
                (identifier, encode(row)),
            )
        return row

    def marker(self, row):
        c = self.c
        payload = validate_payload("capture_sync_marker", row["payload"])
        transport = Transport.model_validate(row["transport"]).model_dump()
        parse_time(row["occurred_at"])
        pid, rid = row["participant_id"], payload["recording_id"]
        with c.db.transaction() as conn:
            self.participant(conn, pid)
            if (
                payload["clock_calibration_id"]
                and not conn.execute(
                    "SELECT 1 FROM clock_calibrations WHERE id=?",
                    (payload["clock_calibration_id"],),
                ).fetchone()
            ):
                raise ValueError("同步标记引用的时钟校准不存在")
            old = conn.execute(
                "SELECT body FROM capture_events WHERE event_id=?", (row["event_id"],)
            ).fetchone()
            identity = {
                "event_id": row["event_id"],
                "participant_id": pid,
                "occurred_at": row["occurred_at"],
                "payload": payload,
                "transport": transport,
            }
            if old:
                existing = json.loads(old[0])
                if any(existing[k] != v for k, v in identity.items()):
                    raise ValueError("同步标记编号冲突")
                return existing
            if conn.execute(
                "SELECT 1 FROM capture_events WHERE json_extract(body,'$.payload.marker_id')=?",
                (payload["marker_id"],),
            ).fetchone():
                raise ValueError("marker_id 已存在")
            number = conn.execute(
                "SELECT COALESCE(MAX(capture_sequence_no),0)+1 FROM capture_events WHERE recording_id=?",
                (rid,),
            ).fetchone()[0]
            body = {
                **identity,
                "schema_version": SCHEMA_VERSION,
                "event_name": "capture_sync_marker",
                "actor": "system",
                "session_id": None,
                "task_id": None,
                "seat_no": None,
                "sequence_no": None,
                "recorded_at": c.now(),
                "recording_id": rid,
                "capture_sequence_no": number,
            }
            conn.execute(
                "INSERT INTO capture_events VALUES(?,?,?,?,?)",
                (row["event_id"], rid, pid, number, encode(body)),
            )
            return body

    def import_bundle(self, bundle, source_dir):
        c = self.c
        source_dir = Path(source_dir)
        report = {"media": 0, "markers": 0, "anchors": 0, "missing_media": []}
        for row in bundle.get("clock_calibrations", []):
            self.calibration(row)
        # Markers describe actual display; no command-line invocation is treated as a display.
        for marker in bundle.get("capture_events", []):
            self.marker(marker)
            report["markers"] += 1
        with c.db.transaction() as conn:

            def put(kind, rid, pid, body):
                self.participant(conn, pid)
                identifier = f"{kind}:{rid}"
                old = conn.execute(
                    "SELECT body FROM capture_records WHERE id=?", (identifier,)
                ).fetchone()
                if old and old[0] != encode(body):
                    raise ValueError(f"{kind} 记录已有不同内容；使用新版本编号")
                conn.execute(
                    "INSERT OR IGNORE INTO capture_records VALUES(?,?,?,?)",
                    (identifier, kind, pid, encode(body)),
                )

            for item in bundle.get("media_manifest", []):
                for key in (
                    "recording_id",
                    "participant_id",
                    "file_ref",
                    "segment",
                    "recording_started_at",
                    "recording_ended_at",
                    "duration_ms",
                    "width",
                    "height",
                    "frame_rate",
                    "known_gaps",
                ):
                    if key not in item:
                        raise ValueError(f"媒体清单缺少 {key}")
                parse_time(item["recording_started_at"])
                parse_time(item["recording_ended_at"])
                if (
                    item["duration_ms"] <= 0
                    or item["width"] <= 0
                    or item["height"] <= 0
                    or item["frame_rate"] <= 0
                ):
                    raise ValueError("媒体时长、分辨率或帧率无效")
                source = (source_dir / item["file_ref"]).resolve()
                body = dict(item)
                if source.is_file():
                    raw = source.read_bytes()
                    ref = f"capture/media/{digest(item['recording_id'])[:20]}/{digest(raw)[:20]}{source.suffix}"
                    atomic_write(c.settings.data_dir / ref, raw)
                    body.update(storage_ref=ref, sha256=digest(raw), archive_status="archived")
                    probe = self.probe(source)
                    body["media_verified"] = probe is not None
                    if probe:
                        stream = probe["streams"][0]
                        actual = {
                            "width": stream["width"],
                            "height": stream["height"],
                            "frame_rate": float(Fraction(stream["avg_frame_rate"])),
                            "duration_ms": float(probe["format"]["duration"]) * 1000,
                        }
                        if any(abs(item[k] - actual[k]) > max(1, actual[k] * 0.02) for k in actual):
                            raise ValueError("清单参数与实际媒体不一致")
                        body["probe"] = actual
                else:
                    body.update(storage_ref=None, archive_status="missing")
                    report["missing_media"].append(item["recording_id"])
                put("media", item["recording_id"], item["participant_id"], body)
                report["media"] += 1
            for link in bundle.get("recording_sessions", []):
                media = conn.execute(
                    "SELECT body FROM capture_records WHERE id=?",
                    ("media:" + link["recording_id"],),
                ).fetchone()
                session = c.db.session(conn, link["session_id"])
                if not media or not session:
                    raise ValueError("录屏或会话不存在")
                media = json.loads(media[0])
                if (
                    session["participant_id"] != media["participant_id"]
                    or not 0
                    <= link["video_start_ms"]
                    < link["video_end_ms"]
                    <= media["duration_ms"]
                ):
                    raise ValueError("录屏身份或会话 PTS 范围无效")
                old = conn.execute(
                    "SELECT video_end_ms FROM recording_sessions WHERE recording_id=? AND session_id=? AND video_start_ms=?",
                    (link["recording_id"], link["session_id"], link["video_start_ms"]),
                ).fetchone()
                if old and old[0] != link["video_end_ms"]:
                    raise ValueError("录屏绑定范围冲突")
                conn.execute(
                    "INSERT OR IGNORE INTO recording_sessions VALUES(?,?,?,?)",
                    (
                        link["recording_id"],
                        link["session_id"],
                        link["video_start_ms"],
                        link["video_end_ms"],
                    ),
                )
            for anchor in bundle.get("sync_anchors", []):
                media = conn.execute(
                    "SELECT participant_id,body FROM capture_records WHERE id=?",
                    ("media:" + anchor["recording_id"],),
                ).fetchone()
                marker = conn.execute(
                    "SELECT body FROM capture_events WHERE recording_id=? AND json_extract(body,'$.payload.marker_id')=?",
                    (anchor["recording_id"], anchor["marker_id"]),
                ).fetchone()
                if not media or not marker:
                    raise ValueError("锚点缺少媒体或实际显示记录")
                marker = json.loads(marker[0])
                meta = json.loads(media[1])
                if (
                    not 0 <= anchor["video_pts_ms"] <= meta["duration_ms"]
                    or anchor["estimated_error_ms"] < 0
                    or not anchor["confirmation_method"]
                ):
                    raise ValueError("锚点 PTS 或核验方式无效")
                if (
                    anchor["displayed_at"] != marker["payload"]["displayed_at"]
                    or anchor.get("clock_calibration_id")
                    != marker["payload"]["clock_calibration_id"]
                    or marker["participant_id"] != media[0]
                ):
                    raise ValueError("锚点与原始显示记录不一致")
                anchor = dict(anchor)
                anchor["pts_verified"] = False
                if meta.get("storage_ref") and self.ffprobe:
                    frames = self.probe(
                        c.settings.data_dir / meta["storage_ref"], anchor["video_pts_ms"]
                    )
                    pts = [
                        float(f["best_effort_timestamp_time"]) * 1000
                        for f in frames["frames"]
                        if "best_effort_timestamp_time" in f
                    ]
                    if (
                        not pts
                        or min(abs(p - anchor["video_pts_ms"]) for p in pts)
                        > anchor["estimated_error_ms"]
                    ):
                        raise ValueError("锚点不匹配实际媒体 PTS 或误差范围")
                    anchor["pts_verified"] = True
                put("anchor", anchor["recording_id"] + ":" + anchor["marker_id"], media[0], anchor)
                report["anchors"] += 1
            for kind in (
                "annotations",
                "artifact_ratings",
                "retrospective",
                "conditions",
                "field_records",
                "research_files",
            ):
                for item in bundle.get(kind, []):
                    session = c.db.session(conn, item["session_id"])
                    if not session or session["participant_id"] != item["participant_id"]:
                        raise ValueError("课后资料与会话身份不匹配")
                    if kind == "research_files":
                        from app.services.files import resolve_ref

                        item = dict(item)
                        path = resolve_ref(source_dir, item["file_ref"])
                        if not path.is_file():
                            item.update(archive_status="missing", storage_ref=None)
                        else:
                            raw = path.read_bytes()
                            ref = f"research/{session['id']}/{item['record_id']}/{path.name}"
                            resolve_ref(c.settings.data_dir, ref)
                            atomic_write(c.settings.data_dir / ref, raw)
                            item.update(
                                archive_status="archived", storage_ref=ref, sha256=digest(raw)
                            )
                    if kind == "artifact_ratings":
                        if not all(
                            item.get(k)
                            for k in ("rubric_version", "rater_id", "dimension", "rating_status")
                        ):
                            raise ValueError("评分缺少量规、评分者、维度或状态")
                        if item.get("submission_id"):
                            sub = c.owned(conn, "submissions", item["submission_id"], session["id"])
                            if sub["status"] != "SUCCEEDED":
                                raise ValueError("评分提交尚未成功")
                        elif item.get("fallback_revision_id"):
                            c.owned(
                                conn, "code_revisions", item["fallback_revision_id"], session["id"]
                            )
                        else:
                            raise ValueError("评分必须指向实际提交或兜底版本")
                    put(kind, item["record_id"], item["participant_id"], item)
        return report
