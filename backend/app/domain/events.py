from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Nonnegative = Annotated[int, Field(ge=0)]
Reason = Literal["close", "run", "send", "leave", "submit", "end", "paste"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def timezone_required(cls, value, info):
        if info.field_name in {"occurred_at", "edit_started_at", "last_edit_at"}:
            parse_time(value)
        return value


class EditRange(StrictModel):
    start: Nonnegative
    end: Nonnegative

    @field_validator("end")
    @classmethod
    def valid_end(cls, value, info):
        if value < info.data.get("start", 0):
            raise ValueError("end 必须大于等于 start")
        return value


class EditChange(StrictModel):
    operation: Literal["insert", "delete", "replace"]
    inserted_text: str
    deleted_text: str
    edit_range: EditRange


EDIT = {
    "edit_changes": Annotated[list[EditChange], Field(min_length=1)],
    "content_length_after": Nonnegative,
    "edit_started_at": str,
    "last_edit_at": str,
    "flush_reason": Reason,
}
FIELDS = {
    "task_started": {"entry_page": str},
    "task_viewed": {"task_content_version": str},
    "example_opened": {"example_id": Id},
    "task_revisited": {"from_page": Literal["workbench"]},
    "example_closed": {
        "example_id": Id,
        "last_position_sec": Annotated[float, Field(ge=0)],
        "watched_seconds": Annotated[float, Field(ge=0)],
        "close_reason": Literal["manual", "navigate", "end"],
    },
    "workbench_entered": {"entry_source": Literal["first", "return"]},
    "planner_opened": {},
    "planner_edited": {**EDIT, "base_plan_revision": Nonnegative, "plan_revision": Nonnegative},
    "file_attached": {
        "attachment_id": Id,
        "file_name": str,
        "file_type": str,
        "file_size": Nonnegative,
    },
    "attachment_failed": {
        "attachment_id": Id,
        "failure_stage": str,
        "error_type": str,
        "error_message": str,
    },
    "ai_request_edited": {**EDIT, "draft_id": Id},
    "ai_request_sent": {
        "request_id": Id,
        "draft_id": Id,
        "message_text": str,
        "attachment_ids": list[Id],
        "retry_of_request_id": Id | None,
    },
    "ai_response_received": {
        "request_id": Id,
        "response_id": Id,
        "response_text": str,
        "model_name": str,
        "response_status": Literal["SUCCEEDED"],
    },
    "ai_response_failed": {
        "request_id": Id,
        "failure_stage": str,
        "error_type": str,
        "error_message": str,
        "retryable": bool,
    },
    "ai_response_copied": {"response_id": Id, "content_type": Literal["text", "code"]},
    "code_pasted": {
        "pasted_text": str,
        "paste_source": Literal["AI response", "other"],
        "source_response_id": Id | None,
        "edit_range": EditRange,
        "code_revision": Nonnegative,
    },
    "code_edited": {**EDIT, "base_code_revision": Nonnegative, "code_revision": Nonnegative},
    "preview_run": {
        "run_id": Id,
        "code_revision": Nonnegative,
        "code_snapshot_ref": str | None,
        "save_status": Literal["saved", "failed"],
    },
    "preview_ready": {"run_id": Id},
    "preview_error_detected": {
        "run_id": Id,
        "error_id": Id,
        "error_phase": Literal["load", "interaction"],
        "error_type": str,
        "error_message": str,
        "line": Nonnegative | None,
        "column": Nonnegative | None,
        "stack": str | None,
    },
    "preview_error_copied": {"error_id": Id},
    "preview_interacted": {
        "run_id": Id,
        "interaction_type": Literal["click", "change", "submit"],
        "target": str,
        "outcome": str | None,
    },
    "window_left": {"leave_reason": str},
    "window_returned": {"return_reason": str},
    "submit_dialog_opened": {},
    "submit_confirmed": {
        "submission_id": Id,
        "code_revision": Nonnegative,
        "plan_revision": Nonnegative,
        "snapshot_id": Id,
    },
    "submit_cancelled": {},
    "submit_succeeded": {"submission_id": Id, "snapshot_id": Id},
    "submit_failed": {
        "submission_id": Id,
        "error_type": str,
        "error_message": str,
        "retryable": bool,
    },
    "task_ended": {"end_reason": str},
}
SYSTEM_EVENTS = {
    "attachment_failed",
    "ai_response_received",
    "ai_response_failed",
    "preview_ready",
    "preview_error_detected",
    "submit_succeeded",
    "submit_failed",
}
# These actions are recorded by their business services, never trusted from /events/batch.
SERVICE_EVENTS = SYSTEM_EVENTS | {
    "task_started",
    "task_ended",
    "file_attached",
    "ai_request_sent",
    "preview_run",
    "preview_interacted",
    "submit_confirmed",
}
REGISTRY = {
    name: create_model(
        name, __base__=StrictModel, **{key: (typ, ...) for key, typ in fields.items()}
    )
    for name, fields in FIELDS.items()
}


def parse_time(value: str):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return result


def validate_payload(name, payload):
    if name not in REGISTRY:
        raise ValueError("未知事件名")
    result = REGISTRY[name].model_validate(payload).model_dump()
    if "edit_started_at" in result:
        if parse_time(result["edit_started_at"]) > parse_time(result["last_edit_at"]):
            raise ValueError("编辑起止时间不合法")
    return result


class ClientEvent(StrictModel):
    event_id: Id
    event_name: str
    actor: Literal["student"]
    occurred_at: str
    client_sequence_no: Annotated[int, Field(ge=1)]
    payload: dict
