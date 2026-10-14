"""Researcher-controlled stop/exclusion ledger, kept outside replaceable data backups."""

import json

from app.domain.errors import DomainError
from app.repositories.database import encode
from app.services.files import atomic_write


class ResearchAccess:
    def __init__(self, core):
        self.c = core
        self.path = core.settings.restrictions_path

    def records(self):
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def require(self, participant_id):
        record = self.records().get(participant_id)
        if record:
            raise DomainError("RESEARCH_STOPPED", "本次研究采集已停止，请联系研究者。", 403)

    def stop(self, participant_id, reason, policy_version, exclude=False):
        if not reason.strip() or not policy_version.strip():
            raise ValueError("必须提供处理依据与研究者批准的制度版本")
        with self.c.db.transaction() as conn:
            if not conn.execute(
                "SELECT 1 FROM participants WHERE id=?", (participant_id,)
            ).fetchone():
                raise ValueError("参与者不存在")
            records = self.records()
            old = records.get(participant_id, {})
            record = {
                "participant_id": participant_id,
                "stopped_at": old.get("stopped_at", self.c.now()),
                "exclude": exclude or old.get("exclude", False),
                "reason": reason,
                "policy_version": policy_version,
                "external_recording_action": "researcher_must_stop_recording",
            }
            records[participant_id] = record
            atomic_write(self.path, encode(records))
            conn.execute(
                "UPDATE sessions SET status=CASE WHEN started_at IS NULL THEN 'ABANDONED' ELSE 'ENDED' END, ended_at=COALESCE(ended_at,?),lease_until=? WHERE participant_id=? AND status IN ('PREPARING','ACTIVE','ENDING')",
                (self.c.now(), self.c.now(), participant_id),
            )
        return record

    def inventory(self, participant_id):
        with self.c.db.read() as conn:
            sessions = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM sessions WHERE participant_id=?", (participant_id,)
                )
            ]
            bindings = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM recording_sessions WHERE session_id IN (SELECT id FROM sessions WHERE participant_id=?)",
                    (participant_id,),
                )
            ]
        return {
            "participant_id": participant_id,
            "session_ids": sessions,
            "recording_ranges": bindings,
            "restriction": self.records().get(participant_id),
            "manual_review": [
                "shared recordings",
                "previous exports and backups",
                "analysis copies",
                "remote AI copies",
            ],
            "deletion_performed": False,
        }
