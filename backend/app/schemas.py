from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.models import TaskType, InterventionType


# ── Session ──────────────────────────────────────────────
class SessionCreate(BaseModel):
    user_id: str
    task_type: TaskType
    task_description: Optional[str] = None


class SessionOut(BaseModel):
    id: UUID
    user_id: str
    task_type: TaskType
    task_description: Optional[str]
    created_at: datetime
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Interaction log ───────────────────────────────────────
class LogCreate(BaseModel):
    event_type: str = Field(..., pattern="^(prompt|edit|verify|message)$")
    content: str


class LogOut(BaseModel):
    id: UUID
    session_id: UUID
    event_type: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


# ── Metacognitive state ───────────────────────────────────
class MetacogStateOut(BaseModel):
    id: UUID
    session_id: UUID
    planning: float
    monitoring: float
    evaluation: float
    timestamp: datetime

    class Config:
        from_attributes = True


# ── Intervention ──────────────────────────────────────────
class InterventionOut(BaseModel):
    id: UUID
    session_id: UUID
    intervention_type: InterventionType
    trigger_reason: Optional[str]
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── WebSocket message schemas ─────────────────────────────
class WSIncoming(BaseModel):
    """Message sent from client over WebSocket."""
    event_type: str          # prompt | edit | verify | message
    content: str


class WSOutgoing(BaseModel):
    """Message pushed from server over WebSocket."""
    type: str                # state_update | intervention | ack | error
    payload: dict
