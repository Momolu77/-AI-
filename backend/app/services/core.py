import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import ValidationError

from app.domain.errors import DomainError
from app.domain.events import (
    CONTRACT,
    SERVICE_EVENTS,
    SYSTEM_EVENTS,
    ClientEvent,
    parse_time,
    validate_payload,
)
from app.repositories.database import Database, encode
from app.services.files import atomic_write, digest
from app.settings import ROOT


def uid():
    return str(uuid.uuid4())


class Core:
    def __init__(self, settings, clock=None):
        self.settings = settings
        self.db = Database(settings.database)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.producer_id = "server-" + uid()
        self.producer_seq = 0
        from app.services.collection import CollectionService

        self.collection = CollectionService(self)
        from app.services.research_access import ResearchAccess

        self.research_access = ResearchAccess(self)

    def now(self):
        return self.clock().isoformat(timespec="milliseconds")

    def initialize(self):
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db.migrate()
        for path in sorted((ROOT / "config/tasks").glob("*.json")):
            task = json.loads(path.read_text(encoding="utf-8"))
            self.collection.publish(task)
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO task_configs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                    (task["task_id"], encode(task)),
                )

    def seed(self):
        token_file = self.settings.data_dir / "seat-tokens.json"
        tokens = (
            json.loads(token_file.read_text(encoding="utf-8"))
            if token_file.exists()
            else {f"{i:02}": secrets.token_urlsafe(24) for i in range(1, 4)}
        )
        with self.db.transaction() as conn:
            for seat, token in tokens.items():
                conn.execute(
                    "INSERT OR IGNORE INTO seats VALUES(?,?,?,?)",
                    (
                        seat,
                        digest(token),
                        self.settings.task_id,
                        (self.clock() + timedelta(days=365)).isoformat(),
                    ),
                )
                binding = conn.execute(
                    "SELECT participant_id FROM seat_participants WHERE seat_no=?", (seat,)
                ).fetchone()
                if not binding:
                    participant = uid()
                    conn.execute("INSERT INTO participants VALUES(?,?)", (participant, self.now()))
                    conn.execute("INSERT INTO seat_participants VALUES(?,?)", (seat, participant))
                else:
                    participant = binding[0]
                conn.execute(
                    "INSERT OR IGNORE INTO task_assignments VALUES(?,?,?,?)",
                    (uid(), participant, self.settings.task_id, "default"),
                )
        atomic_write(token_file, encode(tokens))
        return tokens

    def token(self, session):
        return jwt.encode(
            {
                "sub": session["participant_id"],
                "sid": session["id"],
                "seat": session["seat_no"],
                "scope": "session",
                "iat": self.clock(),
                "exp": self.clock() + timedelta(hours=8),
            },
            self.settings.secret,
            algorithm="HS256",
        )

    def authenticate(self, bearer):
        try:
            claims = jwt.decode(
                bearer.removeprefix("Bearer "),
                self.settings.secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub", "sid", "scope"]},
            )
            if claims["scope"] != "session":
                raise ValueError("scope")
            with self.db.read() as conn:
                session = self.db.session(conn, claims["sid"])
            if (
                not session
                or session["participant_id"] != claims["sub"]
                or session["seat_no"] != claims["seat"]
            ):
                raise ValueError("identity")
            self.research_access.require(session["participant_id"])
            return session
        except (jwt.PyJWTError, ValueError, KeyError):
            raise DomainError(
                "UNAUTHORIZED", "会话凭据无效或过期，请从座位入口重新进入。", 401
            ) from None

    def public_session(self, session):
        return {
            key: session[key]
            for key in (
                "id",
                "participant_id",
                "seat_no",
                "task_id",
                "task_version",
                "status",
                "started_at",
                "ended_at",
            )
        } | {
            "session_id": session["id"],
            "server_now": self.now(),
            "heartbeat_interval_sec": self.settings.heartbeat,
            "schema_version": session["schema_version"],
            "prerequisite": json.loads(session["prerequisite_json"])
            if session["prerequisite_json"]
            else None,
            "writer_id": session["writer_id"],
            "lease_until": session["lease_until"],
        }

    def claim_writer(self, conn, session, writer_id, resume=True):
        if (
            session["writer_id"]
            and session["writer_id"] != writer_id
            and session["lease_until"]
            and parse_time(session["lease_until"]) > self.clock()
        ):
            raise DomainError(
                "WRITER_CONFLICT", "此会话已在另一个标签页使用，请关闭后等待租约释放。", 409
            )
        if session["detach_at"] and resume:
            self.db.put(
                conn,
                "session_technical",
                uid(),
                session["id"],
                {
                    "kind": "detach_cancelled",
                    "candidate_at": session["detach_at"],
                    "resumed_at": self.now(),
                    "writer_id": writer_id,
                },
            )
        conn.execute(
            "UPDATE sessions SET writer_id=?,lease_until=?,last_seen_at=?,detach_at=CASE WHEN ? THEN NULL ELSE detach_at END WHERE id=?",
            (
                writer_id,
                (self.clock() + timedelta(seconds=60)).isoformat(),
                self.now(),
                resume,
                session["id"],
            ),
        )

    @staticmethod
    def occurrence(data):
        return {
            k: data[k] for k in ("event_id", "occurred_at", "transport") if data.get(k) is not None
        }

    def active(self, conn, sid):
        session = self.db.session(conn, sid)
        if session:
            self.research_access.require(session["participant_id"])
        if not session or session["status"] != "ACTIVE":
            raise DomainError("SESSION_ENDED", "会话已结束，可以查看和导出已有内容。", 409)
        conn.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (self.now(), sid))
        return session

    def owned(self, conn, table, object_id, sid):
        obj = self.db.get(conn, table, object_id, sid)
        if obj is None:
            raise DomainError("NOT_FOUND", "记录不存在。", 404)
        return obj

    def emit(
        self,
        conn,
        sid,
        name,
        payload,
        *,
        actor=None,
        event_id=None,
        occurred_at=None,
        client_sequence_no=None,
        transport=None,
    ):
        s = self.db.session(conn, sid)
        payload = validate_payload(name, payload, s["schema_version"])
        actor = actor or ("system" if name in SYSTEM_EVENTS else "student")
        now = self.now()
        occurred_at = (
            parse_time(occurred_at or now).astimezone(UTC).isoformat(timespec="milliseconds")
        )
        event_id = event_id or uid()
        if transport:
            transport = dict(transport)
            client_sequence_no = transport.get("client_sequence_no") or client_sequence_no
            for parent in transport.get("causal_parent_ids", []):
                row = conn.execute(
                    "SELECT session_id FROM events WHERE event_id=?", (parent,)
                ).fetchone()
                if row and row[0] != sid:
                    raise ValueError("跨会话因果引用")
            calibration = transport.get("clock_calibration_id")
            if (
                calibration
                and not conn.execute(
                    "SELECT 1 FROM clock_calibrations WHERE id=? AND session_id=?",
                    (calibration, sid),
                ).fetchone()
            ):
                raise ValueError("校准引用无效")
        fingerprint = digest(
            encode([sid, name, actor, occurred_at, client_sequence_no, payload, transport])
        )
        old = conn.execute(
            "SELECT fingerprint FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        if old:
            if old[0] != fingerprint:
                raise DomainError("ID_CONFLICT", "相同 event_id 的内容不一致。", 409)
            return "accepted_duplicate"
        conn.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                name,
                actor,
                sid,
                s["participant_id"],
                s["task_id"],
                s["seat_no"],
                occurred_at,
                now,
                s["next_sequence"],
                client_sequence_no,
                encode(payload),
                fingerprint,
            ),
        )
        conn.execute("UPDATE sessions SET next_sequence=next_sequence+1 WHERE id=?", (sid,))
        if transport is None:
            self.producer_seq += 1
            transport = {
                "producer_id": self.producer_id,
                "producer_seq": self.producer_seq,
                "client_sequence_no": None,
                "raw_time": occurred_at,
                "monotonic_ms": None,
                "clock_calibration_id": None,
                "time_source": "server_clock",
                "action_id": None,
                "causal_parent_ids": [],
            }
        conn.execute(
            "INSERT INTO event_transport VALUES(?,?,?)",
            (event_id, s["schema_version"], encode(transport)),
        )
        return "accepted"

    def heartbeat(self, sid, writer_id=None):
        self.expire()
        with self.db.transaction() as conn:
            session = self.db.session(conn, sid)
            if session["status"] in {"PREPARING", "ACTIVE", "ENDING"}:
                self.claim_writer(conn, session, writer_id or session["writer_id"])
                if session["status"] == "ENDING":
                    conn.execute("UPDATE sessions SET status='ACTIVE' WHERE id=?", (sid,))
                session = self.db.session(conn, sid)
        return self.public_session(session) | {"token": self.token(session)}

    def detach(self, sid, persisted=False, occurrence=None):
        with self.db.transaction() as conn:
            s = self.db.session(conn, sid)
            if s["status"] in {"PREPARING", "ACTIVE", "ENDING"}:
                conn.execute(
                    "UPDATE sessions SET detach_at=?,detach_persisted=?,status=? WHERE id=?",
                    (
                        (occurrence or {}).get("occurred_at", self.now()),
                        int(persisted),
                        "ENDING" if s["started_at"] else "PREPARING",
                        sid,
                    ),
                )
                self.db.put(
                    conn,
                    "session_technical",
                    uid(),
                    sid,
                    {
                        "kind": "detach_candidate",
                        "persisted": persisted,
                        "recorded_at": self.now(),
                        "occurrence": occurrence,
                    },
                )
        return {"status": "candidate"}

    def end(self, sid, reason="student_end", actor="student", occurrence=None):
        with self.db.transaction() as conn:
            session = self.db.session(conn, sid)
            if session["status"] in {"ENDED", "ABANDONED"}:
                return self.public_session(session)
            if not session["started_at"]:
                conn.execute(
                    "UPDATE sessions SET status='ABANDONED',ended_at=? WHERE id=?",
                    (self.now(), sid),
                )
                return self.public_session(self.db.session(conn, sid))
            # Even without a submission, preserve the last acknowledged drafts.
            archive = {
                "session_id": sid,
                "code": self.latest(conn, sid, "code"),
                "plan": self.latest(conn, sid, "plan"),
                "ended_at": self.now(),
                "end_reason": reason,
            }
            atomic_write(self.settings.data_dir / "ended" / f"{sid}.json", encode(archive))
            if session["schema_version"].endswith("v1.3"):
                sent = {r["command"]["draft_id"] for r in self.db.all(conn, "ai_requests", sid)}
                for draft in self.db.all(conn, "request_drafts", sid):
                    if draft["id"] in sent:
                        continue
                    for aid in draft["attachment_ids"]:
                        attachment = self.db.get(conn, "attachments", aid, sid)
                        if attachment and attachment["status"] != "REMOVED":
                            attachment["status"] = "REMOVED"
                            self.db.put(conn, "attachments", aid, sid, attachment)
                            self.emit(
                                conn,
                                sid,
                                "attachment_removed",
                                {
                                    "attachment_id": aid,
                                    "remove_reason": "session_end",
                                    "draft_id": draft["id"],
                                    "draft_revision": draft["revision"],
                                },
                                actor="system",
                            )
            self.emit(
                conn, sid, "task_ended", {"end_reason": reason}, actor=actor, **(occurrence or {})
            )
            conn.execute(
                "UPDATE sessions SET status='ENDED',ended_at=? WHERE id=?", (self.now(), sid)
            )
            return self.public_session(self.db.session(conn, sid))

    def expire(self):
        cutoff = self.clock() - timedelta(seconds=self.settings.session_timeout)
        with self.db.read() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM sessions WHERE status IN ('PREPARING','ACTIVE','ENDING')"
                )
            ]
        for row in rows:
            detached = (
                row["detach_at"]
                and not row["detach_persisted"]
                and parse_time(row["detach_at"]) < self.clock() - timedelta(seconds=15)
            )
            if detached or parse_time(row["last_seen_at"]) < cutoff:
                self.end(
                    row["id"], "page_exit_unresumed" if detached else "timeout_unobserved", "system"
                )

    def batch(self, sid, events):
        results = []
        for raw in events:
            event_id = raw.get("event_id") if isinstance(raw, dict) else None
            try:
                event = ClientEvent.model_validate(raw)
                event.payload = validate_payload(
                    event.event_name, event.payload, event.schema_version
                )
                if event.event_name in SERVICE_EVENTS:
                    raise ValueError("该事件只允许相应业务服务记录")
                occurred = parse_time(event.occurred_at)
                with self.db.transaction() as conn:
                    session = self.db.session(conn, sid)
                    if session["schema_version"] != event.schema_version:
                        raise ValueError("事件版本与会话不一致")
                    if not session["started_at"]:
                        raise ValueError("任务尚未开始")
                    allowed_actor = CONTRACT["events"][event.event_name]["actor"]
                    if allowed_actor != "both" and event.actor != allowed_actor:
                        raise ValueError("事件 actor 不匹配")
                    if allowed_actor == "both" and event.actor != (
                        "system" if event.payload.get("close_reason") == "end" else "student"
                    ):
                        raise ValueError("关闭来源不匹配")
                    if occurred < parse_time(session["started_at"]) - timedelta(
                        seconds=5
                    ) or occurred > self.clock() + timedelta(seconds=30):
                        raise ValueError("发生时间超出会话范围")
                    if session["status"] == "ENDED" and occurred > parse_time(session["ended_at"]):
                        raise ValueError("结束后只能补传结束前的历史事件")
                    if event.event_name == "task_viewed":
                        if event.payload.get("task_content_version") != session["task_version"]:
                            raise ValueError("任务版本不匹配")
                        previous = conn.execute(
                            "SELECT event_id FROM events WHERE session_id=? AND event_name='task_viewed'",
                            (sid,),
                        ).fetchone()
                        if previous and previous[0] != event.event_id:
                            raise ValueError("首次查看只能记录一次")
                    if event.event_name.startswith("example_"):
                        allowed = {x["id"] for x in json.loads(session["task_json"])["examples"]}
                        if event.payload.get("example_id") not in allowed:
                            raise ValueError("示例不属于此任务")
                    if event.event_name in {"ai_response_copied", "ai_response_displayed"}:
                        response = self.owned(
                            conn, "ai_responses", event.payload.get("response_id"), sid
                        )
                        revision = event.payload.get("content_revision", -1)
                        chunks = [
                            r
                            for r in self.db.all(conn, "ai_response_chunks", sid)
                            if r["response_id"] == response["id"]
                            and r["content_revision"] <= revision
                        ]
                        if (
                            revision < 1
                            or not chunks
                            or max(r["content_revision"] for r in chunks) != revision
                        ):
                            raise ValueError("回复历史版本不存在")
                        length = max(r["range"]["end"] for r in chunks)
                        if event.event_name == "ai_response_displayed":
                            p = event.payload
                            if (
                                p["request_id"] != response["request_id"]
                                or p["rendered_range"]["end"] > length
                            ):
                                raise ValueError("回复显示范围或请求引用不匹配")
                            if p["is_visible"] != bool(p["visible_ranges"]) or any(
                                r["start"] < p["rendered_range"]["start"]
                                or r["end"] > p["rendered_range"]["end"]
                                for r in p["visible_ranges"]
                            ):
                                raise ValueError("可见范围超出已呈现范围")
                        elif any(
                            r["end"] > length for r in event.payload.get("selection_ranges") or []
                        ):
                            raise ValueError("复制范围超出回复历史版本")
                    if event.event_name in {"ai_proposal_displayed", "ai_proposal_reviewed"}:
                        p = event.payload
                        proposal = self.owned(conn, "ai_proposals", p.get("proposal_id"), sid)
                        if (
                            p["base_code_revision"] != proposal["base_code_revision"]
                            or p.get("proposal_content_ref", p.get("detail_content_ref"))
                            != proposal["proposal_content_ref"]
                        ):
                            raise ValueError("提议版本引用不匹配")
                    if event.event_name.startswith("resource_"):
                        self.collection.resource(
                            session,
                            event.payload.get("resource_id"),
                            event.payload.get("resource_version"),
                        )
                    if event.event_name == "code_pasted":
                        source = event.payload.get("source_response_id")
                        if event.payload.get("paste_source") == "ai_response":
                            self.owned(conn, "ai_responses", source, sid)
                        elif source is not None:
                            raise ValueError("非 AI 粘贴不能携带回复引用")
                    if event.event_name == "preview_error_copied":
                        self.owned(conn, "preview_logs", event.payload.get("error_id"), sid)
                    status = self.emit(
                        conn,
                        sid,
                        event.event_name,
                        event.payload,
                        actor=event.actor,
                        event_id=event.event_id,
                        occurred_at=event.occurred_at,
                        client_sequence_no=event.client_sequence_no,
                        transport=event.transport.model_dump(),
                    )
                    if session["status"] == "ACTIVE":
                        conn.execute(
                            "UPDATE sessions SET last_seen_at=? WHERE id=?", (self.now(), sid)
                        )
                with self.db.read() as conn:
                    persisted = conn.execute(
                        "SELECT sequence_no,recorded_at FROM events WHERE event_id=?", (event_id,)
                    ).fetchone()
                results.append({"event_id": event_id, "status": status, **dict(persisted)})
            except (ValueError, ValidationError, DomainError) as exc:
                results.append(
                    {
                        "event_id": event_id,
                        "status": "rejected",
                        "reason": str(exc),
                        "retryable": False,
                    }
                )
        return {"results": results}

    def latest(self, conn, sid, kind):
        table = "code_revisions" if kind == "code" else "planner_revisions"
        row = conn.execute(
            f"SELECT id FROM {table} WHERE session_id=? ORDER BY revision_no DESC LIMIT 1", (sid,)
        ).fetchone()
        return (
            self.db.get(conn, table, row[0], sid)
            if row
            else {"revision": 0, "content": "", "content_ref": None}
        )

    def save_revision(self, conn, sid, kind, content, revision, allow_historical=False):
        if len(content.encode("utf-8")) > self.settings.code_max:
            raise DomainError("CONTENT_TOO_LARGE", "内容超过本地保存大小上限。", 413)
        table = "code_revisions" if kind == "code" else "planner_revisions"
        existing = conn.execute(
            f"SELECT id FROM {table} WHERE session_id=? AND revision_no=?", (sid, revision)
        ).fetchone()
        if existing:
            obj = self.db.get(conn, table, existing[0], sid)
            if obj["content"] != content:
                raise DomainError(
                    "REVISION_CONFLICT", "同一版本存在不同内容，请保留本地草稿并重新加载。", 409
                )
            return obj
        latest = self.latest(conn, sid, kind)
        if revision < latest["revision"] and not allow_historical:
            raise DomainError("STALE_REVISION", "版本落后于已保存版本，请保留草稿。", 409)
        object_id = uid()
        folder, suffix = (
            ("code-snapshots", "html") if kind == "code" else ("planner-snapshots", "txt")
        )
        ref = f"{folder}/{sid}/{object_id}.{suffix}"
        atomic_write(self.settings.data_dir / ref, content)
        body = {
            "revision": revision,
            "content": content,
            "content_ref": ref,
            "sha256": digest(content),
            "created_at": self.now(),
        }
        self.db.put(conn, table, object_id, sid, body, revision_no=revision)
        return {"id": object_id, "session_id": sid, **body}

    def save(self, sid, kind, content, revision):
        with self.db.transaction() as conn:
            self.active(conn, sid)
            result = self.save_revision(conn, sid, kind, content, revision, allow_historical=True)
        return result | {f"{kind}_revision": revision, "code_snapshot_ref": result["content_ref"]}

    def state(self, sid):
        with self.db.read() as conn:
            return {
                "code": self.latest(conn, sid, "code"),
                "plan": self.latest(conn, sid, "plan"),
                **{
                    table: self.db.all(conn, table, sid)
                    for table in (
                        "attachments",
                        "ai_requests",
                        "ai_responses",
                        "submissions",
                        "preview_runs",
                        "preview_logs",
                        "request_drafts",
                        "draft_revisions",
                        "resource_references",
                        "ai_proposals",
                        "proposal_applications",
                    )
                },
                "task_viewed": bool(
                    conn.execute(
                        "SELECT 1 FROM events WHERE session_id=? AND event_name='task_viewed'",
                        (sid,),
                    ).fetchone()
                ),
            }
