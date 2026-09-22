import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import ValidationError

from app.domain.errors import DomainError
from app.domain.events import (
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

    def now(self):
        return self.clock().isoformat(timespec="milliseconds")

    def initialize(self):
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db.migrate()
        task = json.loads(
            (ROOT / "config/tasks" / f"{self.settings.task_id}.json").read_text(encoding="utf-8")
        )
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
        }

    def active(self, conn, sid):
        session = self.db.session(conn, sid)
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
    ):
        payload = validate_payload(name, payload)
        actor = actor or ("system" if name in SYSTEM_EVENTS else "student")
        now = self.now()
        occurred_at = (
            parse_time(occurred_at or now).astimezone(UTC).isoformat(timespec="milliseconds")
        )
        event_id = event_id or uid()
        fingerprint = digest(encode([sid, name, actor, occurred_at, client_sequence_no, payload]))
        old = conn.execute(
            "SELECT fingerprint FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        if old:
            if old[0] != fingerprint:
                raise DomainError("ID_CONFLICT", "相同 event_id 的内容不一致。", 409)
            return "accepted_duplicate"
        s = self.db.session(conn, sid)
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
        return "accepted"

    def bootstrap(self, seat, token):
        self.expire()
        with self.db.transaction() as conn:
            source = conn.execute("SELECT * FROM seats WHERE seat_no=?", (seat,)).fetchone()
            if (
                not source
                or not secrets.compare_digest(source["token_hash"], digest(token))
                or parse_time(source["expires_at"]) < self.clock()
            ):
                raise DomainError("INVALID_SEAT", "座位入口无效或已过期。", 401)
            existing = conn.execute(
                "SELECT id FROM sessions WHERE seat_no=? AND status='ACTIVE'", (seat,)
            ).fetchone()
            if existing:
                session = self.db.session(conn, existing[0])
            else:
                task = json.loads(
                    conn.execute(
                        "SELECT body FROM task_configs WHERE id=?", (source["task_id"],)
                    ).fetchone()[0]
                )
                sid, participant, now = uid(), uid(), self.now()
                conn.execute(
                    "INSERT INTO sessions(id,participant_id,seat_no,task_id,task_version,task_json,status,started_at,last_seen_at) VALUES(?,?,?,?,?,?,'ACTIVE',?,?)",
                    (
                        sid,
                        participant,
                        seat,
                        task["task_id"],
                        task["version"],
                        encode(task),
                        now,
                        now,
                    ),
                )
                self.emit(conn, sid, "task_started", {"entry_page": "task"})
                session = self.db.session(conn, sid)
        return self.public_session(session) | {"token": self.token(session)}

    def heartbeat(self, sid):
        self.expire()
        with self.db.transaction() as conn:
            session = self.active(conn, sid)
        return self.public_session(session) | {"token": self.token(session)}

    def end(self, sid, reason="student", actor="student"):
        with self.db.transaction() as conn:
            session = self.db.session(conn, sid)
            if session["status"] == "ENDED":
                return self.public_session(session)
            # Even without a submission, preserve the last acknowledged drafts.
            archive = {
                "session_id": sid,
                "code": self.latest(conn, sid, "code"),
                "plan": self.latest(conn, sid, "plan"),
                "ended_at": self.now(),
                "end_reason": reason,
            }
            atomic_write(self.settings.data_dir / "ended" / f"{sid}.json", encode(archive))
            self.emit(conn, sid, "task_ended", {"end_reason": reason}, actor=actor)
            conn.execute(
                "UPDATE sessions SET status='ENDED',ended_at=? WHERE id=?", (self.now(), sid)
            )
            return self.public_session(self.db.session(conn, sid))

    def expire(self):
        cutoff = self.clock() - timedelta(seconds=self.settings.session_timeout)
        with self.db.read() as conn:
            ids = [
                row["id"]
                for row in conn.execute("SELECT * FROM sessions WHERE status='ACTIVE'")
                if parse_time(row["last_seen_at"]) < cutoff
            ]
        for sid in ids:
            self.end(sid, "timeout", "system")

    def batch(self, sid, events):
        results = []
        for raw in events:
            event_id = raw.get("event_id") if isinstance(raw, dict) else None
            try:
                event = ClientEvent.model_validate(raw)
                if event.event_name in SERVICE_EVENTS:
                    raise ValueError("该事件只允许相应业务服务记录")
                occurred = parse_time(event.occurred_at)
                with self.db.transaction() as conn:
                    session = self.db.session(conn, sid)
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
                    if event.event_name == "ai_response_copied":
                        self.owned(conn, "ai_responses", event.payload.get("response_id"), sid)
                    if event.event_name == "code_pasted":
                        source = event.payload.get("source_response_id")
                        if event.payload.get("paste_source") == "AI response":
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
                        actor="student",
                        event_id=event.event_id,
                        occurred_at=event.occurred_at,
                        client_sequence_no=event.client_sequence_no,
                    )
                    if session["status"] == "ACTIVE":
                        conn.execute(
                            "UPDATE sessions SET last_seen_at=? WHERE id=?", (self.now(), sid)
                        )
                results.append({"event_id": event_id, "status": status})
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
            result = self.save_revision(conn, sid, kind, content, revision)
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
                    )
                },
                "task_viewed": bool(
                    conn.execute(
                        "SELECT 1 FROM events WHERE session_id=? AND event_name='task_viewed'",
                        (sid,),
                    ).fetchone()
                ),
            }
