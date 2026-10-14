from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.domain.events import Id, Nonnegative, StrictModel, Transport, parse_time


class Occurrence(StrictModel):
    event_id: Id
    occurred_at: str
    transport: Transport

    @field_validator("occurred_at")
    @classmethod
    def timestamp(cls, value):
        parse_time(value)
        return value


class Prepare(StrictModel):
    task_id: Id
    assignment_id: Id | None = None
    writer_id: Id


class Detach(Occurrence):
    persisted: bool = False


class BackgroundResponse(StrictModel):
    question_id: Id
    answer_value: str | int | float | None


class Prerequisite(Occurrence):
    version: str
    responses: list[BackgroundResponse]


class Draft(StrictModel):
    content: str
    revision: Nonnegative
    attachment_ids: list[Id] = Field(default_factory=list)
    reference_ids: list[Id] = Field(default_factory=list)


class Reference(Occurrence):
    reference_id: Id
    resource_id: Id
    resource_version: str
    draft_revision: Nonnegative
    page: int | None = None
    fragment: str | None = None
    reference_purpose: (
        Literal[
            "teaching_goal",
            "knowledge_point",
            "interaction_idea",
            "feedback_design",
            "uncertainty",
            "other",
        ]
        | None
    ) = None
    reference_note: Annotated[str, Field(max_length=2000)] | None = None


class RemoveReference(Occurrence):
    draft_revision: Nonnegative


class RemoveAttachment(RemoveReference):
    draft_id: Id


class Decision(Occurrence):
    decision: Literal["accept", "reject"]
    display_event_id: Id | None = None
    decision_display_elapsed_ms: float | None = None


class Application(StrictModel):
    application_id: Id
    retry_of_application_id: Id | None = None
    current_revision: Nonnegative


class Bootstrap(StrictModel):
    seat: str
    token: str


class Revision(StrictModel):
    content: str
    revision: Nonnegative


class Run(Revision, Occurrence):
    run_id: Id
    occurred_at: str


class Submission(Occurrence):
    submission_id: Id
    snapshot_id: Id
    code: str
    plan: str
    design_rationale: Annotated[str, Field(max_length=20000)] | None = None
    code_revision: Nonnegative
    plan_revision: Nonnegative
    occurred_at: str


class AIRequest(Occurrence):
    request_id: Id
    draft_id: Id
    message_text: Annotated[str, Field(max_length=50000)]
    attachment_ids: Annotated[list[Id], Field(max_length=10)]
    retry_of_request_id: Id | None = None
    occurred_at: str
    draft_revision: Nonnegative
    reference_ids: list[Id] = Field(default_factory=list)
    base_code_revision: Nonnegative


class PreviewMessage(Occurrence):
    message_id: Id
    channel: str
    kind: Literal["ready", "log", "warn", "error", "interaction"]
    text: Annotated[str, Field(max_length=20000)] = ""
    error_type: str = "Error"
    error_phase: Literal["load", "interaction"] = "load"
    line: Nonnegative | None = None
    column: Nonnegative | None = None
    stack: str | None = None
    interaction_type: Literal["activate", "change", "input_commit", "submit"] = "activate"
    target: dict = Field(default_factory=lambda: {"tag": "", "id": None, "role": None, "label": ""})
    outcome: str | None = None
    outcome_source: Literal["artifact", "unknown"] = "unknown"
    load_id: Id | None = None


class PreviewLoad(Occurrence):
    load_id: Id
    state: Literal["loading", "failed", "timeout"]
    reason: Annotated[str, Field(max_length=500)]


class Batch(StrictModel):
    session_id: Id
    events: Annotated[list, Field(max_length=50)]
