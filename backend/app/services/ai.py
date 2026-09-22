import asyncio
import json
from typing import Protocol

import httpx

from app.domain.errors import DomainError
from app.services.core import uid
from app.settings import ROOT


class ProviderFailure(Exception):
    def __init__(self, error_type, message, retryable=True, stage="response"):
        super().__init__(message)
        self.error_type, self.retryable, self.stage = error_type, retryable, stage


class AIProvider(Protocol):
    model: str

    def stream_chat(self, messages, attachments, request_id): ...


class FakeProvider:
    model = "fake-local-v1"

    def __init__(self, settings):
        self.settings = settings

    async def stream_chat(self, messages, attachments, request_id):
        scenario = self.settings.fake_scenario
        if scenario == "rate_limited":
            raise ProviderFailure("RATE_LIMITED", "模拟服务限流，请稍后重试。", stage="request")
        if scenario == "first_token_timeout":
            await asyncio.sleep(self.settings.first_token_timeout + 1)
        text = "这是本地测试模型的固定回复。请自行选择教材单元、调整词汇并检查游戏。\n"
        if attachments:
            text += f"已读取 {len(attachments)} 个附件中的文字。\n"
        text += (
            "\n```html\n"
            + (ROOT / "tests/fixtures/game.html").read_text(encoding="utf-8")
            + "\n```"
        )
        for i in range(0, len(text), 48):
            await asyncio.sleep(0.12 if scenario == "slow_stream" else 0.008)
            yield text[i : i + 48]
            if scenario == "partial_then_error" and i >= 96:
                raise ProviderFailure("CONNECTION_LOST", "模拟回复中断，已保留收到的内容。")


class DeepSeekProvider:
    def __init__(self, settings, transport=None):
        self.settings, self.transport, self.model = settings, transport, settings.deepseek_model

    async def stream_chat(self, messages, attachments, request_id):
        timeout = httpx.Timeout(self.settings.total_timeout, connect=self.settings.connect_timeout)
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST",
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.deepseek_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "max_tokens": 8192,
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ProviderFailure(
                            f"HTTP_{response.status_code}",
                            f"AI 服务返回 {response.status_code}。",
                            response.status_code == 429 or response.status_code >= 500,
                            "request",
                        )
                    finished = False
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        content = line[5:].strip()
                        if content == "[DONE]":
                            finished = True
                            break
                        try:
                            value = json.loads(content)
                            choices = value.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content")
                                if delta:
                                    yield delta
                        except (json.JSONDecodeError, TypeError, KeyError) as exc:
                            raise ProviderFailure(
                                "INVALID_STREAM", "AI 返回了无效流数据。", False
                            ) from exc
                    if not finished:
                        raise ProviderFailure(
                            "INCOMPLETE_STREAM", "AI 连接提前结束，已保留回复片段。"
                        )
        except httpx.TimeoutException as exc:
            raise ProviderFailure("NETWORK_TIMEOUT", "AI 网络请求超时。") from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure("NETWORK_ERROR", "AI 网络连接失败。") from exc


class AIService:
    def __init__(self, core, provider=None):
        self.core = core
        self.provider = provider or (
            FakeProvider(core.settings)
            if core.settings.ai_provider == "fake"
            else DeepSeekProvider(core.settings)
        )
        self.semaphore = asyncio.Semaphore(core.settings.ai_concurrency)
        self.tasks = {}

    def create(self, sid, command):
        c, d = self.core, command.model_dump()
        with c.db.transaction() as conn:
            old = c.db.get(conn, "ai_requests", d["request_id"])
            if old:
                if old["session_id"] != sid or old["command"] != d:
                    raise DomainError("ID_CONFLICT", "请求编号已被不同内容使用。", 409)
                return old
            c.active(conn, sid)
            if any(
                r["status"] in {"QUEUED", "STREAMING"} for r in c.db.all(conn, "ai_requests", sid)
            ):
                raise DomainError("AI_BUSY", "当前回复尚未结束。", 409)
            if not d["message_text"].strip() and not d["attachment_ids"]:
                raise DomainError("EMPTY_MESSAGE", "请输入文字或添加可用附件。")
            attachments = [
                c.owned(conn, "attachments", object_id, sid) for object_id in d["attachment_ids"]
            ]
            if any(item["status"] != "READY" for item in attachments):
                raise DomainError(
                    "ATTACHMENT_NOT_READY", "附件未处理完成，请重试或移除失败附件。", 409
                )
            if d["retry_of_request_id"]:
                previous = c.owned(conn, "ai_requests", d["retry_of_request_id"], sid)
                if previous["status"] != "FAILED":
                    raise DomainError("NOT_RETRYABLE", "仅失败请求可以重试。", 409)
            response_id = uid()
            body = {
                "command": d,
                "status": "QUEUED",
                "response_id": response_id,
                "created_at": c.now(),
            }
            c.db.put(conn, "ai_requests", d["request_id"], sid, body)
            c.db.put(
                conn,
                "ai_responses",
                response_id,
                sid,
                {
                    "request_id": d["request_id"],
                    "response_text": "",
                    "model_name": self.provider.model,
                    "status": "PENDING",
                    "created_at": c.now(),
                },
            )
            c.emit(
                conn,
                sid,
                "ai_request_sent",
                {
                    k: d[k]
                    for k in (
                        "request_id",
                        "draft_id",
                        "message_text",
                        "attachment_ids",
                        "retry_of_request_id",
                    )
                },
                occurred_at=d["occurred_at"],
            )
        task = asyncio.create_task(self.generate(sid, d["request_id"], attachments))
        self.tasks[d["request_id"]] = task
        task.add_done_callback(lambda _: self.tasks.pop(d["request_id"], None))
        return {"id": d["request_id"], "session_id": sid, **body}

    def read(self, sid, request_id):
        with self.core.db.read() as conn:
            request = self.core.owned(conn, "ai_requests", request_id, sid)
            response = self.core.owned(conn, "ai_responses", request["response_id"], sid)
        return request, response

    def checkpoint(self, sid, request_id, text, status, error=None):
        c = self.core
        with c.db.transaction() as conn:
            request = c.owned(conn, "ai_requests", request_id, sid)
            response = c.owned(conn, "ai_responses", request["response_id"], sid)
            request["status"] = status
            response.update(
                response_text=text, status="PARTIAL" if status == "FAILED" and text else status
            )
            if status == "SUCCEEDED":
                c.emit(
                    conn,
                    sid,
                    "ai_response_received",
                    {
                        "request_id": request_id,
                        "response_id": response["id"],
                        "response_text": text,
                        "model_name": response["model_name"],
                        "response_status": status,
                    },
                )
            if error:
                details = {
                    "request_id": request_id,
                    "failure_stage": error.stage,
                    "error_type": error.error_type,
                    "error_message": str(error),
                    "retryable": error.retryable,
                }
                request["error"] = details
                c.emit(conn, sid, "ai_response_failed", details)
            c.db.put(conn, "ai_requests", request_id, sid, request)
            c.db.put(conn, "ai_responses", response["id"], sid, response)

    async def generate(self, sid, request_id, attachments):
        text = ""
        try:
            async with self.semaphore:
                request, _ = self.read(sid, request_id)
                with self.core.db.read() as conn:
                    history = self.core.db.all(conn, "ai_requests", sid)
                    responses = {
                        r["request_id"]: r for r in self.core.db.all(conn, "ai_responses", sid)
                    }
                messages = [
                    {
                        "role": "system",
                        "content": "你是教学资源制作助手。根据用户的要求回答；HTML 作品应自包含、支持点击和触摸。不要声称已经验证学生作品。",
                    }
                ]
                for item in history:
                    if item["status"] == "SUCCEEDED":
                        messages.extend(
                            [
                                {"role": "user", "content": item["command"]["message_text"]},
                                {
                                    "role": "assistant",
                                    "content": responses[item["id"]]["response_text"],
                                },
                            ]
                        )
                user_text = request["command"]["message_text"]
                for attachment in attachments:
                    user_text += f"\n\n附件 {attachment['file_name']} 的提取文字：\n{attachment['extracted_text']}"
                messages.append({"role": "user", "content": user_text})
                self.checkpoint(sid, request_id, text, "STREAMING")
                stream = self.provider.stream_chat(messages, attachments, request_id)
                try:
                    async with asyncio.timeout(self.core.settings.total_timeout):
                        first = await asyncio.wait_for(
                            anext(stream), self.core.settings.first_token_timeout
                        )
                        text += first
                        self.checkpoint(sid, request_id, text, "STREAMING")
                        async for chunk in stream:
                            if len(text) + len(chunk) > self.core.settings.max_output:
                                raise ProviderFailure(
                                    "OUTPUT_LIMIT", "回复超过输出长度上限，已保存片段。", False
                                )
                            text += chunk
                            self.checkpoint(sid, request_id, text, "STREAMING")
                finally:
                    await stream.aclose()
                self.checkpoint(sid, request_id, text, "SUCCEEDED")
        except asyncio.CancelledError:
            self.checkpoint(
                sid,
                request_id,
                text,
                "FAILED",
                ProviderFailure("SERVER_STOPPED", "服务停止，回复中断。"),
            )
            raise
        except (TimeoutError, StopAsyncIteration):
            failure = ProviderFailure(
                "FIRST_TOKEN_TIMEOUT" if not text else "TOTAL_TIMEOUT",
                "AI 响应超时或没有返回内容。",
                stage="first_token" if not text else "response",
            )
            self.checkpoint(sid, request_id, text, "FAILED", failure)
        except Exception as exc:
            failure = (
                exc
                if isinstance(exc, ProviderFailure)
                else ProviderFailure("PROVIDER_ERROR", "AI 处理失败，已保留回复片段。")
            )
            self.checkpoint(sid, request_id, text, "FAILED", failure)

    async def stream(self, sid, request_id, offset=0):
        while True:
            request, response = self.read(sid, request_id)
            text = response["response_text"]
            if offset < len(text):
                yield (
                    "event: chunk\ndata: "
                    + json.dumps(
                        {"delta": text[offset:], "response_id": response["id"]}, ensure_ascii=False
                    )
                    + "\n\n"
                )
                offset = len(text)
            if request["status"] in {"SUCCEEDED", "FAILED"}:
                yield (
                    "event: done\ndata: "
                    + json.dumps({"request": request, "response": response}, ensure_ascii=False)
                    + "\n\n"
                )
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.05)

    def recover(self):
        with self.core.db.read() as conn:
            rows = conn.execute("SELECT id,session_id,body FROM ai_requests").fetchall()
        for row in rows:
            if json.loads(row["body"])["status"] in {"QUEUED", "STREAMING"}:
                _, response = self.read(row["session_id"], row["id"])
                self.checkpoint(
                    row["session_id"],
                    row["id"],
                    response["response_text"],
                    "FAILED",
                    ProviderFailure("SERVER_RESTARTED", "服务重启，已保存上次收到的内容。"),
                )

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
