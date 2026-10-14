import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import TypeAdapter

from app.api.json_response import RequestIdRoute
from app.domain.commands import (
    AIRequest,
    Application,
    Batch,
    Bootstrap,
    Decision,
    Detach,
    Draft,
    Occurrence,
    Prepare,
    Prerequisite,
    PreviewLoad,
    PreviewMessage,
    Reference,
    RemoveAttachment,
    RemoveReference,
    Revision,
    Run,
    Submission,
)
from app.domain.errors import DomainError
from app.domain.events import Id
from app.settings import ROOT

router = APIRouter(prefix="/api/v1", route_class=RequestIdRoute)


def session(
    request: Request, authorization: str = Header(default=""), x_writer_id: str = Header(default="")
):
    c = request.app.state.core
    if request.method not in {"GET", "HEAD"}:
        c.expire()
    s = c.authenticate(authorization)
    if request.method not in {"GET", "HEAD"} and s["status"] in {"PREPARING", "ACTIVE", "ENDING"}:
        if not x_writer_id:
            raise DomainError("WRITER_REQUIRED", "缺少标签页写入凭据。", 409)
        with c.db.transaction() as conn:
            c.claim_writer(conn, c.db.session(conn, s["id"]), x_writer_id, resume=False)
    return s


Session = Annotated[dict, Depends(session)]


@router.post("/entry/bootstrap")
def bootstrap(body: Bootstrap, request: Request):
    return request.app.state.core.collection.entry(body.seat, body.token)


@router.get("/tasks")
def tasks(request: Request, authorization: str = Header(default="")):
    c = request.app.state.core.collection
    return {"tasks": c.tasks(c.identity(authorization))}


@router.post("/session/bootstrap")
def prepare(body: Prepare, request: Request, authorization: str = Header(default="")):
    c = request.app.state.core.collection
    return c.prepare(c.identity(authorization), body.task_id, body.assignment_id, body.writer_id)


@router.post("/session/prerequisite")
def prerequisite(body: Prerequisite, request: Request, s: Session):
    return request.app.state.core.collection.prerequisite(s["id"], body)


@router.post("/session/start")
def start(body: Occurrence, request: Request, s: Session):
    return request.app.state.core.collection.start(s["id"], body)


@router.post("/session/detach")
def detach(body: Detach, request: Request, s: Session):
    return request.app.state.core.detach(
        s["id"], body.persisted, body.model_dump(exclude={"persisted"})
    )


@router.get("/clock")
def clock(request: Request, s: Session):
    return {"server_time": request.app.state.core.now()}


@router.post("/clock/calibrations")
def calibration(body: dict, request: Request, s: Session):
    from app.domain.events import parse_time
    from app.repositories.database import encode

    for field in ("client_send_time", "server_time", "client_receive_time"):
        parse_time(body[field])
    if body.get("round_trip_ms", -1) < 0 or body.get("uncertainty_ms", -1) < 0:
        raise DomainError("INVALID_CALIBRATION", "校准误差无效。")
    TypeAdapter(Id).validate_python(body["id"])
    with request.app.state.core.db.transaction() as conn:
        old = conn.execute(
            "SELECT session_id,body FROM clock_calibrations WHERE id=?", (body["id"],)
        ).fetchone()
        if old and (old[0] != s["id"] or old[1] != encode(body)):
            raise DomainError("ID_CONFLICT", "校准编号冲突。", 409)
        conn.execute(
            "INSERT OR IGNORE INTO clock_calibrations VALUES(?,?,?)",
            (body["id"], s["id"], encode(body)),
        )
    return body


@router.get("/session/me")
def me(request: Request, s: Session):
    return request.app.state.core.public_session(s)


@router.post("/session/heartbeat")
def heartbeat(request: Request, s: Session):
    return request.app.state.core.heartbeat(s["id"])


@router.post("/session/end")
def end(body: Occurrence, request: Request, s: Session):
    c = request.app.state.core
    return c.end(s["id"], occurrence=c.occurrence(body.model_dump()))


@router.get("/tasks/{task_id}")
def task(task_id: str, s: Session, request: Request):
    if task_id != s["task_id"]:
        raise DomainError("NOT_FOUND", "任务不存在。", 404)
    return request.app.state.core.collection.task(s)


@router.get("/tasks/{task_id}/examples")
def examples(task_id: str, s: Session, request: Request):
    if task_id != s["task_id"]:
        raise DomainError("NOT_FOUND", "任务不存在。", 404)
    return {"examples": request.app.state.core.collection.task(s).get("examples", [])}


@router.get("/tasks/{task_id}/resources")
def resources(task_id: str, s: Session, request: Request):
    if task_id != s["task_id"]:
        raise DomainError("NOT_FOUND", "任务不存在。", 404)
    return {"resources": request.app.state.core.collection.resources(s)}


@router.get("/resources/{resource_id}/versions/{version}")
def resource(resource_id: str, version: str, s: Session, request: Request, download: bool = False):
    c = request.app.state.core
    item = c.collection.resource(s, resource_id, version)
    if download:
        return FileResponse(
            c.settings.data_dir / item["storage_ref"],
            media_type=item["mime"],
            headers={
                "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
            },
        )
    return item


@router.put("/drafts/{draft_id}")
def draft(draft_id: str, body: Draft, request: Request, s: Session):
    return request.app.state.core.collection.save_draft(s["id"], draft_id, body)


@router.post("/drafts/{draft_id}/references")
def reference(draft_id: str, body: Reference, request: Request, s: Session):
    return request.app.state.core.collection.reference(s["id"], draft_id, body)


@router.delete("/drafts/{draft_id}/references/{reference_id}")
def remove_reference(
    draft_id: str, reference_id: str, body: RemoveReference, request: Request, s: Session
):
    return request.app.state.core.collection.reference(s["id"], draft_id, body, reference_id)


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
            "Content-Security-Policy": "sandbox allow-scripts allow-forms; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'",
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


@router.post("/workbench/preview/{run_id}/load")
def preview_load(run_id: str, body: PreviewLoad, request: Request, s: Session):
    return request.app.state.preview.load(s["id"], run_id, body)


@router.get("/workbench/preview/{run_id}")
def run_status(run_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        r = c.owned(conn, "preview_runs", run_id, s["id"])
    return r | (request.app.state.preview.result(r) if r["status"] in {"SAVED", "READY"} else {})


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
def remove_attachment(attachment_id: str, body: RemoveAttachment, request: Request, s: Session):
    return request.app.state.attachments.remove(s["id"], attachment_id, body)


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
        getattr(body, key) != previous["command"][key]
        for key in (
            "message_text",
            "attachment_ids",
            "reference_ids",
            "draft_id",
            "draft_revision",
            "base_code_revision",
        )
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
        rows = c.db.all(conn, "submissions", s["id"])
        succeeded = sorted(
            [r for r in rows if r["status"] == "SUCCEEDED"], key=lambda r: r.get("submission_no", 0)
        )
        return {
            "submissions": rows,
            "final_submission_id": succeeded[-1]["id"] if succeeded else None,
            "final_snapshot_id": succeeded[-1]["snapshot_id"] if succeeded else None,
            "last_success_at": succeeded[-1].get("completed_at") if succeeded else None,
            "fallback_source": None if succeeded else "last_acknowledged_drafts",
        }


@router.get("/submissions/{submission_id}")
def submission_status(submission_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        return c.owned(conn, "submissions", submission_id, s["id"])


@router.get("/ai/proposals/{proposal_id}")
def proposal(proposal_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        return c.owned(conn, "ai_proposals", proposal_id, s["id"])


@router.post("/ai/proposals/{proposal_id}/decision")
def decision(proposal_id: str, body: Decision, request: Request, s: Session):
    return request.app.state.ai.proposals.decide(s["id"], proposal_id, body)


@router.post("/ai/proposals/{proposal_id}/applications")
def apply_proposal(proposal_id: str, body: Application, request: Request, s: Session):
    return request.app.state.ai.proposals.apply(s["id"], proposal_id, body)


@router.get("/ai/proposals/{proposal_id}/applications/{application_id}")
def application(proposal_id: str, application_id: str, request: Request, s: Session):
    c = request.app.state.core
    with c.db.read() as conn:
        item = c.owned(conn, "proposal_applications", application_id, s["id"])
        if item["proposal_id"] != proposal_id:
            raise DomainError("NOT_FOUND", "应用记录不存在。", 404)
        return item


def install_media(app):
    @app.get("/media/examples/{example_id}")
    def media(example_id: str):
        # Public synthetic teaching examples contain no session data.
        if example_id not in {"demo-local", "demo-web"}:
            raise DomainError("NOT_FOUND", "视频不存在。", 404)
        path = ROOT / (
            "config/examples/demo.webm"
            if example_id == "demo-local"
            else "config/examples/demo.html"
        )
        if not path.exists():
            raise DomainError(
                "MEDIA_MISSING", "本地视频暂不可用，可以重试或直接进入工作区。", 404, True
            )
        return FileResponse(
            path,
            media_type="video/webm" if example_id == "demo-local" else "text/html",
            headers={
                "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"
            },
        )
