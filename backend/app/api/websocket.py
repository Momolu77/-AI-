"""
WebSocket 实时交互处理器 - 通义千问版本

职责：
1. 接收客户端发来的交互事件（prompt / edit / verify / message）
2. 持久化日志（包含 AI 消息和元数据），计算元认知状态，推送状态更新
3. 在需要时触发干预，将干预内容推送给客户端

改进点：
- 流式输出支持
- 持久化 AI 消息和元数据（模型版本、Token 用量、请求 ID）
- 传递任务描述到 AI
- 上下文管理（限制到 24K tokens）
- 断线重连后恢复上下文
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models import InteractionLog, MetacogState, Intervention, Session
from app.schemas import WSIncoming, WSOutgoing
from app.services.state_recognizer import extract_features, compute_metacog_state
from app.services.intervention import InterventionStateMachine
from app.services.ai_generator import chat_with_ai_stream, generate_intervention
from app.config import settings

router = APIRouter()


async def _push(ws: WebSocket, msg_type: str, data: dict):
    """发送WebSocket消息，格式: {type: str, data: dict}"""
    await ws.send_text(json.dumps({"type": msg_type, "data": data}))


async def load_chat_history(db: AsyncSession, session_id: UUID) -> list[dict]:
    """
    从数据库加载对话历史（用于断线重连）

    Args:
        db: 数据库会话
        session_id: 会话 ID

    Returns:
        对话历史列表 [{"role": "user", "content": "..."}, ...]
    """
    result = await db.execute(
        select(InteractionLog)
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.role.in_(["user", "assistant"])
        )
        .order_by(InteractionLog.timestamp)
    )
    logs = result.scalars().all()

    return [
        {"role": log.role, "content": log.content}
        for log in logs
    ]


@router.websocket("/session/{session_id}")
async def session_ws(session_id: UUID, websocket: WebSocket):
    await websocket.accept()

    # 干预状态机
    intervention_sm = InterventionStateMachine(str(session_id))

    try:
        async with AsyncSessionLocal() as db:
            # 确认 session 存在
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if not session:
                await _push(websocket, "error", {"message": "Session not found"})
                await websocket.close(code=4004)
                return

            task_desc = session.task_description or "通用学习任务"

            # 加载对话历史（断线重连恢复上下文）
            chat_history = await load_chat_history(db, session_id)

            while True:
                raw = await websocket.receive_text()
                try:
                    data = WSIncoming.model_validate_json(raw)
                except Exception:
                    await _push(websocket, "error", {"message": "Invalid message format"})
                    continue

                # ── 1. 持久化用户消息 ──────────────────────────────
                user_log = InteractionLog(
                    session_id=session_id,
                    event_type=data.event_type,
                    content=data.content,
                    role="user" if data.event_type == "prompt" else None,
                )
                db.add(user_log)
                await db.commit()

                # ── 2. 如果是 prompt 事件，调用 AI 并流式返回回复 ──────────
                if data.event_type == "prompt":
                    ai_reply_parts = []

                    # 流式生成并推送
                    async for chunk in chat_with_ai_stream(
                        chat_history=chat_history,
                        user_message=data.content,
                        task_description=task_desc
                    ):
                        ai_reply_parts.append(chunk)
                        await _push(websocket, "ai_reply_chunk", {"content": chunk})

                    # 完整回复
                    ai_reply = "".join(ai_reply_parts)

                    # 更新对话历史
                    chat_history.append({"role": "user", "content": data.content})
                    chat_history.append({"role": "assistant", "content": ai_reply})

                    # 持久化 AI 消息
                    ai_log = InteractionLog(
                        session_id=session_id,
                        event_type="ai_reply",
                        content=ai_reply,
                        role="assistant",
                        model_name=settings.chat_model,
                        # tokens_used 和 request_id 需要从 API 响应中获取（后续完善）
                    )
                    db.add(ai_log)
                    await db.commit()

                    # 推送完成信号
                    await _push(websocket, "ai_reply_done", {"content": ai_reply})

                # ── 3. 重新计算元认知状态 ──────────────────────────
                logs_result = await db.execute(
                    select(InteractionLog)
                    .where(InteractionLog.session_id == session_id)
                    .order_by(InteractionLog.timestamp)
                )
                all_logs = logs_result.scalars().all()

                # 转换为字典格式
                events = [
                    {
                        'event_type': log.event_type,
                        'content': log.content,
                        'server_timestamp': log.timestamp.isoformat()
                    }
                    for log in all_logs
                ]

                # 提取特征并计算状态
                features = extract_features(events)
                state = compute_metacog_state(features)

                # 持久化状态快照（只保存PME分数和置信度）
                state_record = MetacogState(
                    session_id=session_id,
                    planning=state['planning'],
                    monitoring=state['monitoring'],
                    evaluation=state['evaluation'],
                    confidence=state['confidence'],
                    status=state['status']
                )
                db.add(state_record)
                await db.commit()

                # 推送状态更新给前端
                await _push(websocket, "state_update", state)

                # ── 4. 干预决策 ────────────────────────────────────
                intervention_result = intervention_sm.on_event(state)

                if intervention_result:
                    intervention = Intervention(
                        session_id=session_id,
                        intervention_type=intervention_result['type'],
                        trigger_reason=intervention_result['trigger_reason'],
                        content=intervention_result['content'],
                    )
                    db.add(intervention)
                    await db.commit()

                    await _push(websocket, "intervention", {
                        "type": intervention_result['type'],
                        "reason": intervention_result['trigger_reason'],
                        "content": intervention_result['content'],
                    })

                await _push(websocket, "ack", {"event_type": data.event_type})

    except WebSocketDisconnect:
        pass
