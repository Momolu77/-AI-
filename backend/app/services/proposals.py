"""Explicit proposals; a decision never changes the editor or runs the artifact."""

import json
import re

from app.domain.errors import DomainError
from app.repositories.database import encode
from app.services.files import atomic_write


def u16len(text):
    return len(text.encode("utf-16-le")) // 2


class ProposalService:
    def __init__(self, core):
        self.c = core

    def create(self, sid, request, response):
        from app.services.core import uid

        c = self.c
        for block in re.findall(r"```proposal\s*\n(.*?)\n```", response["response_text"], re.S):
            try:
                item = json.loads(block)
                if set(item) != {"title", "code"} or not all(
                    isinstance(v, str) for v in item.values()
                ):
                    continue
                if len(item["code"].encode("utf-8")) > c.settings.code_max:
                    continue
            except (ValueError, TypeError):
                continue
            pid = uid()
            ref = f"proposals/{sid}/{pid}.json"
            body = {
                **item,
                "response_id": response["id"],
                "base_code_revision": request["command"]["base_code_revision"],
                "proposal_content_ref": ref,
                "decision": None,
            }
            atomic_write(c.settings.data_dir / ref, encode(body))
            with c.db.transaction() as conn:
                c.db.put(conn, "ai_proposals", pid, sid, body)
                c.emit(
                    conn,
                    sid,
                    "ai_proposal_created",
                    {
                        k: v
                        for k, v in {"proposal_id": pid, **body}.items()
                        if k
                        in {
                            "proposal_id",
                            "response_id",
                            "base_code_revision",
                            "proposal_content_ref",
                        }
                    },
                )

    def decide(self, sid, pid, command):
        c = self.c
        with c.db.transaction() as conn:
            p = c.owned(conn, "ai_proposals", pid, sid)
            if p.get("decision_command"):
                if p["decision_command"] != command.model_dump():
                    raise DomainError("DECISION_FROZEN", "此提议已作出决定。", 409)
                return p
            c.active(conn, sid)
            if command.display_event_id:
                row = conn.execute(
                    "SELECT payload_json FROM events WHERE event_id=? AND session_id=? AND event_name='ai_proposal_displayed'",
                    (command.display_event_id, sid),
                ).fetchone()
                if not row or json.loads(row[0])["proposal_id"] != pid:
                    raise DomainError(
                        "DISPLAY_MISSING", "提议显示记录尚未同步，请重试。", 409, True
                    )
            p.update(decision=command.decision, decision_command=command.model_dump())
            c.db.put(conn, "ai_proposals", pid, sid, p)
            c.emit(
                conn,
                sid,
                "ai_proposal_decided",
                {
                    "proposal_id": pid,
                    "decision": command.decision,
                    "base_code_revision": p["base_code_revision"],
                    "display_event_id": command.display_event_id,
                    "decision_display_elapsed_ms": command.decision_display_elapsed_ms,
                },
                **c.occurrence(command.model_dump()),
            )
            return p

    def apply(self, sid, pid, command):
        c = self.c
        with c.db.transaction() as conn:
            p = c.owned(conn, "ai_proposals", pid, sid)
            old = c.db.get(conn, "proposal_applications", command.application_id)
            if old:
                if (
                    old["session_id"] != sid
                    or old["proposal_id"] != pid
                    or old["command"] != command.model_dump()
                ):
                    raise DomainError("ID_CONFLICT", "应用编号冲突。", 409)
                return old
            c.active(conn, sid)
            if p["decision"] != "accept":
                raise DomainError("ACCEPT_REQUIRED", "请先逐项接受提议。", 409)
            if command.retry_of_application_id:
                prev = c.owned(conn, "proposal_applications", command.retry_of_application_id, sid)
                if prev["proposal_id"] != pid or prev["status"] != "FAILED":
                    raise DomainError("RETRY_MISMATCH", "原应用记录不可重试。", 409)
            latest = c.latest(conn, sid, "code")
            common = {
                "proposal_id": pid,
                "application_id": command.application_id,
                "retry_of_application_id": command.retry_of_application_id,
            }
            result = {**common, "command": command.model_dump()}
            try:
                if (
                    latest["revision"] != p["base_code_revision"]
                    or latest["revision"] != command.current_revision
                ):
                    raise DomainError(
                        "STALE_BASE", "代码已变更；请查看差异后手动合并，或请求新的提议。", 409
                    )
                revision = latest["revision"] + 1
                change = {
                    "operation": "replace",
                    "inserted_text": p["code"],
                    "deleted_text": latest["content"],
                    "edit_range": {"start": 0, "end": u16len(latest["content"])},
                    "base_revision": latest["revision"],
                    "result_revision": revision,
                }
                saved = c.save_revision(conn, sid, "code", p["code"], revision)
                result.update(status="APPLIED", code_revision=revision, content=saved["content"])
                c.emit(
                    conn,
                    sid,
                    "ai_proposal_applied",
                    {
                        **common,
                        "base_code_revision": latest["revision"],
                        "code_revision": revision,
                        "edit_changes": [change],
                    },
                )
            except (OSError, DomainError) as exc:
                result.update(
                    status="FAILED",
                    error_message=str(exc),
                    error_type=getattr(exc, "code", type(exc).__name__),
                )
                c.emit(
                    conn,
                    sid,
                    "ai_proposal_failed",
                    {
                        **common,
                        "failure_stage": "apply",
                        "error_type": result["error_type"],
                        "error_message": str(exc),
                        "retryable": isinstance(exc, OSError),
                    },
                )
            c.db.put(conn, "proposal_applications", command.application_id, sid, result)
            return {"id": command.application_id, "session_id": sid, **result}
