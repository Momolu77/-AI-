import json

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.domain.errors import DomainError


class RequestIdRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            key = request.headers.get("Idempotency-Key")
            path = request.url.path
            field = (
                "submission_id"
                if path == "/api/v1/submissions"
                else "run_id"
                if path == "/api/v1/workbench/preview/run"
                else "request_id"
                if path.startswith("/api/v1/ai/requests")
                else None
            )
            if key and field and request.method == "POST":
                command = await request.json()
                if not isinstance(command, dict) or command.get(field) != key:
                    raise DomainError(
                        "IDEMPOTENCY_KEY_MISMATCH", f"Idempotency-Key 必须与 {field} 相同。", 409
                    )
            response = await original(request)
            if isinstance(response, JSONResponse):
                body = json.loads(response.body)
                if isinstance(body, dict):
                    body["request_id"] = request.state.request_id
                    # AI objects carry their domain ID as `id`; request_id here is HTTP tracing.
                    return JSONResponse(
                        body,
                        status_code=response.status_code,
                        headers={
                            k: v for k, v in response.headers.items() if k != "content-length"
                        },
                    )
            return response

        return handle
