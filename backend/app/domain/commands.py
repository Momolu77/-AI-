from typing import Annotated, Literal

from pydantic import Field

from app.domain.events import Id, Nonnegative, StrictModel


class Bootstrap(StrictModel):
    seat: str
    token: str


class Revision(StrictModel):
    content: str
    revision: Nonnegative


class Run(Revision):
    run_id: Id
    occurred_at: str


class Submission(StrictModel):
    submission_id: Id
    snapshot_id: Id
    code: str
    plan: str
    code_revision: Nonnegative
    plan_revision: Nonnegative
    occurred_at: str


class AIRequest(StrictModel):
    request_id: Id
    draft_id: Id
    message_text: Annotated[str, Field(max_length=50000)]
    attachment_ids: Annotated[list[Id], Field(max_length=10)]
    retry_of_request_id: Id | None = None
    occurred_at: str


class PreviewMessage(StrictModel):
    message_id: Id
    channel: str
    kind: Literal["ready", "log", "warn", "error", "interaction"]
    text: Annotated[str, Field(max_length=20000)] = ""
    error_type: str = "Error"
    error_phase: Literal["load", "interaction"] = "load"
    line: Nonnegative | None = None
    column: Nonnegative | None = None
    stack: str | None = None
    interaction_type: Literal["click", "change", "submit"] = "click"
    target: Annotated[str, Field(max_length=500)] = ""
    outcome: str | None = None


class Batch(StrictModel):
    session_id: Id
    events: Annotated[list, Field(max_length=50)]
