from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum

from app.database import Base


class TaskType(str, enum.Enum):
    subject = "subject"
    writing = "writing"
    problem_solving = "problem_solving"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=False, index=True)
    task_type = Column(Enum(TaskType), nullable=False)
    task_description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    logs = relationship("InteractionLog", back_populates="session", cascade="all, delete-orphan")
    states = relationship("MetacogState", back_populates="session", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="session", cascade="all, delete-orphan")


class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    event_type = Column(String(32), nullable=False)   # prompt / edit / verify / message / ai_reply
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # 新增：AI 相关元数据
    role = Column(String(16), nullable=True)  # user / assistant / system
    model_name = Column(String(64), nullable=True)  # qwen3.8-flash / qwen3.7-flash
    tokens_used = Column(JSON, nullable=True)  # {'prompt': 123, 'completion': 456}
    request_id = Column(String(128), nullable=True)  # 阿里云请求ID

    session = relationship("Session", back_populates="logs")


class MetacogState(Base):
    __tablename__ = "metacog_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    planning = Column(Float, nullable=True)
    monitoring = Column(Float, nullable=True)
    evaluation = Column(Float, nullable=True)
    confidence = Column(JSON, nullable=True)  # {'planning': 0.75, 'monitoring': 1.0, ...}
    status = Column(JSON, nullable=True)      # {'planning': 'observed', ...}
    timestamp = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="states")


class InterventionType(str, enum.Enum):
    metacog_prompt = "metacog_prompt"
    process_scaffold = "process_scaffold"
    reflection_prompt = "reflection_prompt"
    strategy_advice = "strategy_advice"


class Intervention(Base):
    __tablename__ = "interventions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    intervention_type = Column(Enum(InterventionType), nullable=False)
    trigger_reason = Column(String(128), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="interventions")
