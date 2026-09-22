import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import TypeAdapter

from app.api.json_response import RequestIdRoute
from app.domain.commands import (
    AIRequest,
    Batch,
    Bootstrap,
    PreviewMessage,
    Revision,
    Run,
    Submission,
)
from app.domain.errors import DomainError
from app.domain.events import Id
from app.settings import ROOT

router = APIRouter(prefix="/api/v1", route_class=RequestIdRoute)


def session(request: Request, authorization: str = Header(default="")):
    return request.app.state.core.authenticate(authorization)


Session = Annotated[dict, Depends(session)]


@router.post("/session/bootstrap")
def bootstrap(body: Bootstrap, request: Request):
    return request.app.state.core.bootstrap(body.seat, body.token)


@router.get("/session/me")
def me(request: Request, s: Session):
    return request.app.state.core.public_session(s)


@router.post("/session/heartbeat")
def heartbeat(request: Request, s: Session):
    return request.app.state.core.heartbeat(s["id"])


@router.post("/session/end")
def end(request: Request, s: Session):
    return request.app.state.core.end(s["id"])


@router.get("/tasks/{task_id}")
def task(task_id: str, s: Session, request: Request):
    if task_id != s["task_id"]:
        raise DomainError("NOT_FOUND", "任务不存在。", 404)
    task = json.loads(s["task_json"])
    settings = request.app.state.core.settings
    return task | {
        "upload": {"max_bytes": settings.attachment_max, "types": settings.attachment_types},
        "ai_provider": settings.ai_provider,
    }


@router.get("/tasks/{task_id}/examples")
def examples(task_id: str, s: Session):
    if task_id != s["task_id"]:
        raise DomainError("NOT_FOUND", "任务不存在。", 404)
    return {"examples": json.loads(s["task_json"])["examples"]}


@router.post("/events/batch")
def events(body: Batch, request: Request, s: Session):
    if body.session_id != s["id"]:
        raise DomainError("FORBIDDEN", "会话不匹配。", 403)
    return request.app.state.core.batch(s["id"], body.events)


@router.get("/workbench/state")
def state(request: Request, s: Session):
    return request.app.state.core.state(s["id"])


@router.put("/workbench/code")
def code(body: Revision, request: Request, s: Session):
    return request.app.state.core.save(s["id"], "code", body.content, body.revision)


@router.put("/workbench/plan")
def plan(body: Revision, request: Request, s: Session):
    return request.app.state.core.save(s["id"], "plan", body.content, body.revision)


@router.post("/workbench/preview/run")
def run(body: Run, request: Request, s: Session):
    return request.app.state.preview.run(s["id"], body)


@router.get("/preview-content/{run_id}")
def preview_content(run_id: str, signature: str, request: Request):
    path = request.app.state.preview.content(run_id, signature)
    return FileResponse(
        path,
        media_type="text/html",
        headers={
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        },
    )


@router.get("/workbench/preview/{run_id}/logs")
def preview_logs(run_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        c.owned(conn, "preview_runs", run_id, s["id"])
        return {
            "logs": [r for r in c.db.all(conn, "preview_logs", s["id"]) if r["run_id"] == run_id]
        }


@router.post("/workbench/preview/{run_id}/interaction")
def preview_message(run_id: str, body: PreviewMessage, request: Request, s: Session):
    return request.app.state.preview.message(s["id"], run_id, body)


@router.post("/attachments")
async def upload(
    request: Request,
    s: Session,
    attachment_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    try:
        TypeAdapter(Id).validate_python(attachment_id)
    except ValueError:
        raise DomainError("INVALID_ID", "附件编号无效。") from None
    raw = await file.read(request.app.state.core.settings.attachment_max + 1)
    return await asyncio.to_thread(
        request.app.state.attachments.upload,
        s["id"],
        attachment_id,
        file.filename or "file",
        file.content_type or "",
        raw,
    )


@router.get("/attachments/{attachment_id}")
def attachment(attachment_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        return c.owned(conn, "attachments", attachment_id, s["id"])


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: str, request: Request, s: Session):
    return request.app.state.attachments.remove(s["id"], attachment_id)


@router.post("/ai/requests")
async def ai_request(body: AIRequest, request: Request, s: Session):
    return request.app.state.ai.create(s["id"], body)


@router.get("/ai/requests/{request_id}/stream")
async def stream(request_id: str, request: Request, s: Session, offset: int = 0):
    request.app.state.ai.read(s["id"], request_id)
    return StreamingResponse(
        request.app.state.ai.stream(s["id"], request_id, max(0, offset)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ai/requests/{request_id}/retry")
async def retry(request_id: str, body: AIRequest, request: Request, s: Session):
    previous, _ = request.app.state.ai.read(s["id"], request_id)
    if body.retry_of_request_id != request_id or any(
        getattr(body, key) != previous["command"][key] for key in ("message_text", "attachment_ids")
    ):
        raise DomainError("RETRY_MISMATCH", "重试必须保留原始消息和附件。")
    return request.app.state.ai.create(s["id"], body)


@router.post("/submissions")
def submit(body: Submission, request: Request, s: Session):
    return request.app.state.submissions.submit(s["id"], body)


@router.get("/submissions")
def submissions(request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        return {"submissions": c.db.all(conn, "submissions", s["id"])}


def install_media(app):
    @app.get("/media/examples/{example_id}")
    def media(example_id: str):
        # Public synthetic teaching examples contain no session data.
        if example_id != "demo-local":
            raise DomainError("NOT_FOUND", "视频不存在。", 404)
        path = ROOT / "config/examples/demo.webm"
        if not path.exists():
            raise DomainError(
                "MEDIA_MISSING", "本地视频暂不可用，可以重试或直接进入工作区。", 404, True
            )
        return FileResponse(path, media_type="video/webm")
