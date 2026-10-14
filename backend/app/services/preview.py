import json
import secrets
from datetime import timedelta
from pathlib import Path

import jwt

from app.domain.errors import DomainError
from app.services.files import atomic_write

BRIDGE = (Path(__file__).with_name("preview_bridge.js")).read_text(encoding="utf-8")


class PreviewService:
    def __init__(self, core):
        self.core = core

    def run(self, sid, command):
        c, d = self.core, command.model_dump()
        with c.db.read() as conn:
            old = c.db.get(conn, "preview_runs", d["run_id"])
        if old:
            if old["session_id"] != sid or old["command"] != d:
                raise DomainError("ID_CONFLICT", "运行编号已被不同内容使用。", 409)
            if old["status"] == "FAILED":
                raise DomainError("SAVE_FAILED", "本次保存失败，请重新点击运行。", 503, True)
            if old["status"] != "PENDING":
                return self.result(old)
        if not old:
            with c.db.transaction() as conn:
                c.active(conn, sid)
                concurrent = c.db.get(conn, "preview_runs", d["run_id"])
                if concurrent and (concurrent["session_id"] != sid or concurrent["command"] != d):
                    raise DomainError("ID_CONFLICT", "运行编号冲突。", 409)
                if not concurrent:
                    c.db.put(
                        conn,
                        "preview_runs",
                        d["run_id"],
                        sid,
                        {"command": d, "status": "PENDING", "created_at": c.now()},
                    )
        try:
            with c.db.transaction() as conn:
                settled = c.owned(conn, "preview_runs", d["run_id"], sid)
                if settled["status"] in {"SAVED", "READY"}:
                    return self.result(settled)
                if settled["status"] == "FAILED":
                    raise DomainError("SAVE_FAILED", "此尝试已失败，请重新点击运行。", 503, True)
                revision = c.save_revision(
                    conn, sid, "code", d["content"], d["revision"], allow_historical=True
                )
                channel = secrets.token_urlsafe(24)
                bridge = BRIDGE.replace("__RUN__", json.dumps(d["run_id"])).replace(
                    "__CHANNEL__", json.dumps(channel)
                )
                bridge = bridge.replace("__BRIDGE_LINES__", str(BRIDGE.count("\n")))
                # Bridge runs before user scripts; immutable original source is not modified.
                ref = f"previews/{sid}/{d['run_id']}.html"
                html = d["content"]
                if html.lstrip().lower().startswith("<!doctype") and ">" in html:
                    index = html.index(">") + 1
                    html = html[:index] + bridge + html[index:]
                else:
                    html = bridge + html
                atomic_write(c.settings.data_dir / ref, html)
                body = {
                    "command": d,
                    "channel": channel,
                    "content_ref": ref,
                    "revision_id": revision["id"],
                    "bridge_line_count": bridge.count("\n"),
                    "code_revision": d["revision"],
                    "status": "SAVED",
                    "save_status": "saved",
                    "load_attempts": [],
                    "created_at": c.now(),
                }
                c.db.put(conn, "preview_runs", d["run_id"], sid, body)
                c.emit(
                    conn,
                    sid,
                    "preview_run",
                    {
                        "run_id": d["run_id"],
                        "code_revision": d["revision"],
                        "code_snapshot_ref": revision["content_ref"],
                        "save_status": "saved",
                    },
                    **c.occurrence(d),
                )
            return self.result({"id": d["run_id"], "session_id": sid, **body})
        except (OSError, DomainError) as exc:
            with c.db.transaction() as conn:
                c.db.put(
                    conn,
                    "preview_runs",
                    d["run_id"],
                    sid,
                    {
                        "command": d,
                        "status": "FAILED",
                        "save_status": "failed",
                        "created_at": c.now(),
                        "error_type": type(exc).__name__,
                    },
                )
                c.emit(
                    conn,
                    sid,
                    "preview_run",
                    {
                        "run_id": d["run_id"],
                        "code_revision": d["revision"],
                        "code_snapshot_ref": None,
                        "save_status": "failed",
                    },
                    **c.occurrence(d),
                )
                c.emit(
                    conn,
                    sid,
                    "preview_save_failed",
                    {
                        "run_id": d["run_id"],
                        "code_revision": d["revision"],
                        "error_type": type(exc).__name__,
                        "error_message": "无法保存预览",
                        "retryable": True,
                    },
                )
            raise DomainError("SAVE_FAILED", "无法保存预览，原预览保持不变。", 503, True) from exc

    def recover(self):
        from app.domain.commands import Run

        with self.core.db.read() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT session_id,body FROM preview_runs WHERE json_extract(body,'$.status')='PENDING'"
                )
            ]
        for row in rows:
            try:
                self.run(row["session_id"], Run.model_validate(json.loads(row["body"])["command"]))
            except DomainError:
                pass

    def result(self, run):
        token = jwt.encode(
            {
                "scope": "preview",
                "rid": run["id"],
                "sid": run["session_id"],
                "exp": self.core.clock() + timedelta(minutes=10),
            },
            self.core.settings.secret,
            algorithm="HS256",
        )
        return {
            "run_id": run["id"],
            "channel": run["channel"],
            "code_revision": run["code_revision"],
            "save_status": run.get("save_status", "saved"),
            "url": f"/api/v1/preview-content/{run['id']}?signature={token}",
        }

    def content(self, run_id, signature):
        try:
            claims = jwt.decode(signature, self.core.settings.secret, algorithms=["HS256"])
            if claims["scope"] != "preview" or claims["rid"] != run_id:
                raise ValueError()
        except (jwt.PyJWTError, KeyError, ValueError):
            raise DomainError("INVALID_SIGNATURE", "预览地址已过期，请再次运行。", 401) from None
        with self.core.db.read() as conn:
            run = self.core.owned(conn, "preview_runs", run_id, claims["sid"])
            session = self.core.db.session(conn, claims["sid"])
            self.core.research_access.require(session["participant_id"])
        return self.core.settings.data_dir / run["content_ref"]

    def message(self, sid, run_id, message):
        c, d = self.core, message.model_dump()
        with c.db.transaction() as conn:
            session = c.db.session(conn, sid)
            if session["ended_at"] and d["occurred_at"] > session["ended_at"]:
                raise DomainError("SESSION_ENDED", "仅允许补传结束前的预览记录。", 409)
            run = c.owned(conn, "preview_runs", run_id, sid)
            if d["channel"] != run.get("channel"):
                raise DomainError("INVALID_CHANNEL", "预览通道不匹配。", 403)
            old = c.db.get(conn, "preview_logs", d["message_id"], sid)
            if old:
                if old["message"] != d or old["run_id"] != run_id:
                    raise DomainError("ID_CONFLICT", "日志编号冲突。", 409)
                return old
            body = {"run_id": run_id, "message": d, "created_at": c.now()}
            c.db.put(conn, "preview_logs", d["message_id"], sid, body)
            if d["kind"] == "ready" and d.get("load_id"):
                loads = run.setdefault("load_attempts", [])
                load = next((r for r in loads if r["load_id"] == d["load_id"]), None)
                if load:
                    load.update(
                        state="loaded", ready_at=d["occurred_at"], ready_message_id=d["message_id"]
                    )
                    c.db.put(conn, "preview_runs", run_id, sid, run)
            if d["kind"] == "ready" and run["status"] != "READY":
                run.update(status="READY", ready_at=c.now())
                c.db.put(conn, "preview_runs", run_id, sid, run)
                c.emit(conn, sid, "preview_ready", {"run_id": run_id}, **c.occurrence(d))
            elif d["kind"] == "error":
                c.emit(
                    conn,
                    sid,
                    "preview_error_detected",
                    {
                        "run_id": run_id,
                        "error_id": d["message_id"],
                        "error_phase": d["error_phase"],
                        "error_type": d["error_type"],
                        "error_message": d["text"],
                        "line": d["line"],
                        "column": d["column"],
                        "stack": d["stack"],
                    },
                    **c.occurrence(d),
                )
            elif d["kind"] == "interaction":
                c.emit(
                    conn,
                    sid,
                    "preview_interacted",
                    {
                        "run_id": run_id,
                        "interaction_type": d["interaction_type"],
                        "target": d["target"],
                        "outcome": d["outcome"],
                        "outcome_source": d["outcome_source"],
                    },
                    **c.occurrence(d),
                )
        return {"id": d["message_id"], **body}

    def load(self, sid, run_id, command):
        c, data = self.core, command.model_dump()
        with c.db.transaction() as conn:
            session = c.db.session(conn, sid)
            if session["ended_at"] and data["occurred_at"] > session["ended_at"]:
                raise DomainError("SESSION_ENDED", "会话已结束。", 409)
            run = c.owned(conn, "preview_runs", run_id, sid)
            if run["status"] not in {"SAVED", "READY"}:
                raise DomainError("RUN_NOT_SAVED", "运行尚未保存。", 409)
            loads = run.setdefault("load_attempts", [])
            load = next((r for r in loads if r["load_id"] == data["load_id"]), None)
            if load is None:
                if data["state"] != "loading":
                    raise DomainError("LOAD_NOT_FOUND", "缺少加载开始依据。", 409)
                load = {**data, "started_at": data["occurred_at"], "diagnostics": []}
                loads.append(load)
            elif data["state"] != "loading":
                if not any(r["event_id"] == data["event_id"] for r in load["diagnostics"]):
                    load["diagnostics"].append(data)
                if load["state"] != "loaded":
                    load.update(state=data["state"])
            c.db.put(conn, "preview_runs", run_id, sid, run)
            return load
