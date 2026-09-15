from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.database import get_db
from app.models import Session, InteractionLog, MetacogState
from app.schemas import SessionCreate, SessionOut, LogCreate, LogOut, MetacogStateOut
from app.services.state_recognizer import compute_metacog_state

router = APIRouter()


@router.post("/", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = Session(**body.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/logs", response_model=LogOut, status_code=201)
async def add_log(
    session_id: UUID,
    body: LogCreate,
    db: AsyncSession = Depends(get_db),
):
    log = InteractionLog(session_id=session_id, **body.model_dump())
    db.add(log)
    await db.commit()
    await db.refresh(log)

    # 每次写入日志后重新计算状态并保存到数据库
    result = await db.execute(
        select(InteractionLog)
        .where(InteractionLog.session_id == session_id)
        .order_by(InteractionLog.timestamp)
    )
    logs = result.scalars().all()
    state = compute_metacog_state(logs)

    state_record = MetacogState(session_id=session_id, **state)
    db.add(state_record)
    await db.commit()

    return log


@router.get("/{session_id}/states", response_model=list[MetacogStateOut])
async def get_states(session_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MetacogState)
        .where(MetacogState.session_id == session_id)
        .order_by(MetacogState.timestamp)
    )
    return result.scalars().all()
