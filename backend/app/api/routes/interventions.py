from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.database import get_db
from app.models import Intervention, Session, InteractionLog, MetacogState
from app.schemas import InterventionOut
from app.services.intervention import should_intervene, build_intervention_prompt, COOLDOWN_LOGS
from app.services.ai_generator import generate_intervention

router = APIRouter()


@router.post("/{session_id}/trigger", response_model=InterventionOut | None)
async def trigger_intervention(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    主动触发干预检查。WebSocket 路径会自动调用；HTTP 接口供测试或手动触发。
    """
    # 获取最新的元认知状态
    state_result = await db.execute(
        select(MetacogState)
        .where(MetacogState.session_id == session_id)
        .order_by(MetacogState.timestamp.desc())
        .limit(1)
    )
    latest_state = state_result.scalar_one_or_none()
    if not latest_state:
        return None

    state = {
        "planning": latest_state.planning,
        "monitoring": latest_state.monitoring,
        "evaluation": latest_state.evaluation
    }

    # 检查冷却期
    result = await db.execute(
        select(InteractionLog)
        .where(InteractionLog.session_id == session_id)
        .order_by(InteractionLog.timestamp.desc())
        .limit(COOLDOWN_LOGS)
    )
    recent_logs = result.scalars().all()

    intervention_result = await db.execute(
        select(Intervention)
        .where(Intervention.session_id == session_id)
        .order_by(Intervention.created_at.desc())
        .limit(1)
    )
    last_intervention = intervention_result.scalar_one_or_none()

    # 统计上次干预后的日志数
    logs_since = len(recent_logs)
    if last_intervention:
        logs_after = await db.execute(
            select(InteractionLog)
            .where(
                InteractionLog.session_id == session_id,
                InteractionLog.timestamp > last_intervention.created_at,
            )
        )
        logs_since = len(logs_after.scalars().all())

    trigger, i_type, reason = should_intervene(state, 1 if logs_since < COOLDOWN_LOGS else 0)
    if not trigger:
        return None

    # 获取任务描述
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    task_desc = session.task_description or "通用学习任务"

    prompt = build_intervention_prompt(i_type, task_desc, state)
    content = await generate_intervention(prompt)

    intervention = Intervention(
        session_id=session_id,
        intervention_type=i_type,
        trigger_reason=reason,
        content=content,
    )
    db.add(intervention)
    await db.commit()
    await db.refresh(intervention)
    return intervention


@router.get("/{session_id}", response_model=list[InterventionOut])
async def list_interventions(session_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Intervention)
        .where(Intervention.session_id == session_id)
        .order_by(Intervention.created_at)
    )
    return result.scalars().all()
