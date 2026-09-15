"""
AI 生成服务 - 通义千问版本

职责：
1. 主对话：使用 qwen3.8-flash 流式生成回复
2. 判断任务：使用 qwen3.7-flash 结构化输出（目标明确度、追问、纠错、编辑深度）
3. 干预提示：使用本地模板，不调用模型

改进点：
- 启用上下文缓存
- 限制上下文到 24K tokens，超出后摘要
- 持久化消息和元数据
- 流式输出支持（异步迭代器）
- 关闭思考模式（非数学/代码任务）
"""
from __future__ import annotations

import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from app.config import settings


# 初始化阿里云百炼异步客户端
client = AsyncOpenAI(
    api_key=settings.dashscope_api_key,
    base_url=settings.dashscope_base_url,
)


# 系统提示词
SYSTEM_PROMPT = """你是一位专业的学习写作辅导AI助手，专注于帮助学生完成学术写作任务（论文、报告、作文等）。

你的职责：
1. **理解任务**：帮助学生明确写作目标、要求和范围
2. **启发思考**：通过提问引导学生思考，而不是直接给答案
3. **过程支持**：在规划、写作、修改各阶段提供建议
4. **反馈改进**：对学生的草稿提供具体、可操作的反馈

交互原则：
- 鼓励学生自己思考和表达
- 提供脚手架式支持，逐步撤除
- 关注写作过程，而不仅是结果
- 适应学生的水平和需求

当前对话场景：学生正在完成一项写作任务，你需要根据他们的提问和进度提供适当的帮助。"""


def estimate_tokens(messages: list[dict]) -> int:
    """粗略估算消息列表的 token 数（中文约 1.5 字符/token）"""
    total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
    return int(total_chars / 1.5)


def summarize_old_messages(messages: list[dict], keep_recent: int = 4) -> list[dict]:
    """
    摘要旧消息，保留最近 N 条

    Args:
        messages: 消息列表
        keep_recent: 保留最近的消息数量

    Returns:
        摘要后的消息列表
    """
    if len(messages) <= keep_recent:
        return messages

    # 保留系统消息
    system_msgs = [m for m in messages if m["role"] == "system"]
    # 保留最近的消息
    recent_msgs = messages[-keep_recent:]

    # 摘要中间的消息
    old_msgs = messages[len(system_msgs):-keep_recent]
    if old_msgs:
        summary_content = f"[前期对话摘要：共 {len(old_msgs)} 条消息，涵盖任务背景和初步讨论]"
        summary = {"role": "system", "content": summary_content}
        return system_msgs + [summary] + recent_msgs

    return system_msgs + recent_msgs


async def chat_with_ai_stream(
    chat_history: list[dict],
    user_message: str,
    task_description: str = "通用学习任务"
) -> AsyncIterator[str]:
    """
    主对话接口：流式生成 AI 回复

    Args:
        chat_history: 历史对话（不含当前消息）
        user_message: 用户当前消息
        task_description: 任务描述（用于增强上下文）

    Yields:
        生成的文本片段
    """
    # 构建消息列表
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n当前任务：{task_description}"}
    ]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    # 检查上下文长度，超出则摘要
    if estimate_tokens(messages) > settings.max_context_tokens:
        messages = summarize_old_messages(messages, keep_recent=6)

    # 调用通义千问（流式输出，关闭思考模式）
    try:
        completion = await client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            extra_body={"enable_thinking": False},  # 关闭思考模式
            stream=True,
            temperature=0.7,
        )

        async for chunk in completion:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                yield delta.content

    except Exception as e:
        yield f"[生成回复时出错：{str(e)}]"


async def judge_with_structured_output(
    prompt: str,
    output_schema: dict,
) -> dict:
    """
    判断任务接口：结构化输出（目标明确度、追问、纠错、编辑深度）

    Args:
        prompt: 判断提示词
        output_schema: 期望的 JSON Schema

    Returns:
        结构化结果（JSON）
    """
    messages = [
        {"role": "system", "content": "你是一个精确的判断助手，严格按照 JSON Schema 输出结果。"},
        {"role": "user", "content": prompt}
    ]

    try:
        completion = await client.chat.completions.create(
            model=settings.judge_model,
            messages=messages,
            temperature=0,  # 温度设为 0，严格输出
            response_format={"type": "json_object"},  # 强制 JSON 输出
        )

        content = completion.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        return {"error": str(e)}


async def chat_with_ai(chat_history: list[dict], user_message: str) -> str:
    """
    兼容旧接口：非流式生成 AI 回复（用于向后兼容）

    Args:
        chat_history: 历史对话
        user_message: 用户消息

    Returns:
        完整的 AI 回复
    """
    result = []
    async for chunk in chat_with_ai_stream(chat_history, user_message):
        result.append(chunk)
    return "".join(result)


def generate_intervention(intervention_type: str, context: dict) -> str:
    """
    生成干预提示（本地模板，不调用模型）

    Args:
        intervention_type: 干预类型
        context: 上下文信息

    Returns:
        干预内容
    """
    templates = {
        "planning_low": "💡 建议：在开始前，先明确你的写作目标和大纲。可以尝试：1) 列出要点 2) 设定分段结构",
        "monitoring_low": "🔍 提醒：写作过程中要定期检查是否偏离主题。可以尝试：1) 重读已写内容 2) 对照大纲检查",
        "evaluation_low": "✅ 建议：完成一部分后，尝试评估质量。可以尝试：1) 自我检查 2) 向AI请求反馈",
        "stuck": "💪 你似乎遇到了困难。不妨试试：1) 换个角度思考 2) 向我提问 3) 先完成简单的部分",
    }

    return templates.get(intervention_type, "继续加油！")
