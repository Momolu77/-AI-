import asyncio
import json
import logging
import sqlite3
import time
import uuid
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.routes import install_media, router
from app.domain.errors import DomainError
from app.services.ai import AIService
from app.services.attachments import AttachmentService
from app.services.core import Core
from app.services.locking import data_lock
from app.services.preview import PreviewService
from app.services.submissions import SubmissionService
from app.settings import Settings

logger = logging.getLogger("workbench")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


def create_app(settings=None, clock=None, provider=None):
    @asynccontextmanager
    async def lifespan(app):
        core = Core(settings or Settings.load(), clock)
        with ExitStack() as stack:
            stack.enter_context(data_lock(core.settings.data_dir))
            core.initialize()
            app.state.core = core
            app.state.preview = PreviewService(core)
            app.state.attachments = AttachmentService(core)
            app.state.attachments.recover()
            app.state.submissions = SubmissionService(core)
            app.state.ai = AIService(core, provider)
            await asyncio.to_thread(app.state.submissions.recover)
            app.state.ai.recover()

            async def sweeper():
                while True:
                    await asyncio.sleep(min(15, core.settings.heartbeat))
                    try:
                        await asyncio.to_thread(core.expire)
                    except Exception as exc:
                        logger.error(
                            json.dumps(
                                {"event": "session_sweep_failed", "type": type(exc).__name__}
                            )
                        )

            worker = asyncio.create_task(sweeper())
            logger.info(
                json.dumps(
                    {"event": "startup", "version": "0.1.0", "provider": core.settings.ai_provider}
                )
            )
            yield
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            await app.state.ai.close()
            logger.info(json.dumps({"event": "shutdown"}))

    app = FastAPI(title="英语教学资源工作台 · 本地版", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
        )
        return response

    def error_response(request, code, message, status, retryable=False):
        return JSONResponse(
            {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=status,
        )

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(request, exc.code, exc.message, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(
            request,
            "VALIDATION_ERROR",
            "请求格式错误：" + ", ".join(".".join(map(str, e["loc"])) for e in exc.errors()),
            422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, "HTTP_ERROR", str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error(
            json.dumps(
                {
                    "event": "unexpected_error",
                    "request_id": getattr(request.state, "request_id", None),
                    "type": type(exc).__name__,
                }
            )
        )
        return error_response(
            request, "INTERNAL_ERROR", "处理未完成，请保留当前输入并查看本地日志。", 500, True
        )

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        logger.error(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "event": "storage_error",
                    "type": type(exc).__name__,
                }
            )
        )
        return error_response(
            request, "STORAGE_UNAVAILABLE", "本地存储暂不可用，草稿保留后可以重试。", 503, True
        )

    @app.get("/health")
    def health(request: Request):
        core = request.app.state.core
        with core.db.read() as conn:
            conn.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "version": "0.1.0",
            "database": "ok",
            "data_directory": "ok" if core.settings.data_dir.is_dir() else "missing",
            "ai_provider": core.settings.ai_provider,
            "request_id": request.state.request_id,
        }

    app.include_router(router)
    install_media(app)
    return app


app = create_app()
