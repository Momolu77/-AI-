import asyncio
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

import httpx
import jwt
import pytest
from app.domain.errors import DomainError
from app.domain.events import FIELDS, REGISTRY, validate_payload
from app.services.ai import DeepSeekProvider, ProviderFailure
from app.services.attachments import parse_file
from app.services.core import Core
from app.settings import Settings
from docx import Document


def sample(schema):
    if "anyOf" in schema:
        return sample(next(s for s in schema["anyOf"] if s.get("type") != "null"))
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "string":
        return (
            "2026-09-22T08:00:00+00:00"
            if schema.get("title") in {"Edit Started At", "Last Edit At"}
            else "sample"
        )
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return True
    if kind == "array":
        if schema.get("minItems"):
            return [
                {
                    "operation": "insert",
                    "inserted_text": "中😀",
                    "deleted_text": "",
                    "edit_range": {"start": 0, "end": 0},
                }
            ]
        return []
    if "$ref" in schema:
        return {"start": 0, "end": 0}
    return None


@pytest.mark.parametrize("name", list(FIELDS))
def test_all_thirty_contracts_accept_minimum_and_reject_missing_extra_and_type(name):
    schema = REGISTRY[name].model_json_schema()
    payload = {key: sample(value) for key, value in schema["properties"].items()}
    assert validate_payload(name, payload) == payload
    with pytest.raises(ValueError):
        validate_payload(name, {**payload, "unexpected": 1})
    if payload:
        first = next(iter(payload))
        with pytest.raises(ValueError):
            validate_payload(name, {k: v for k, v in payload.items() if k != first})
        with pytest.raises(ValueError):
            validate_payload(name, {**payload, first: {"bad": "type"}})
    assert len(FIELDS) == 30


def test_jwt_and_clock_expiry(settings):
    instant = datetime.now(UTC)
    clock = [instant]
    core = Core(settings, lambda: clock[0])
    core.initialize()
    token = core.seed()["01"]
    info = core.bootstrap("01", token)
    assert core.authenticate("Bearer " + info["token"])["id"] == info["id"]
    with pytest.raises(DomainError):
        core.authenticate(info["token"] + "tampered")
    expired = jwt.encode(
        {
            "sub": "x",
            "sid": "y",
            "scope": "session",
            "iat": instant - timedelta(days=2),
            "exp": instant - timedelta(days=1),
        },
        settings.secret,
        algorithm="HS256",
    )
    with pytest.raises(DomainError):
        core.authenticate(expired)
    clock[0] += timedelta(seconds=settings.session_timeout + 1)
    core.expire()
    core.expire()
    with core.db.read() as conn:
        assert core.db.session(conn, info["id"])["status"] == "ENDED"
        rows = conn.execute(
            "SELECT actor,payload_json FROM events WHERE event_name='task_ended'"
        ).fetchall()
    assert len(rows) == 1 and rows[0]["actor"] == "system"
    assert json.loads(rows[0]["payload_json"])["end_reason"] == "timeout"


def test_real_parsing_and_format_validation(settings):
    assert parse_file("课文.txt", "text/plain", "英语\nhello".encode(), settings) == "英语\nhello"
    document = Document()
    document.add_paragraph("教材 unit 2")
    out = BytesIO()
    document.save(out)
    assert "unit 2" in parse_file("unit.docx", "application/octet-stream", out.getvalue(), settings)
    for name, mime, data in [
        ("bad.pdf", "application/pdf", b"not pdf"),
        ("bad.exe", "text/plain", b"a"),
        ("fake.txt", "text/plain", b"abc\x00"),
        ("wrong.txt", "application/pdf", b"abc"),
        ("empty.txt", "text/plain", b""),
    ]:
        with pytest.raises(Exception):
            parse_file(name, mime, data, settings)
    settings.attachment_max = 2
    with pytest.raises(ValueError):
        parse_file("big.txt", "text/plain", b"123", settings)


def test_deepseek_stream_protocol(settings):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            content='data: {"choices":[{"delta":{"content":"你"}}]}\n\ndata: {"choices":[{"delta":{"content":"好"}}]}\n\ndata: [DONE]\n\n'.encode(),
        )

    async def collect():
        provider = DeepSeekProvider(settings, httpx.MockTransport(handler))
        return "".join(
            [
                piece
                async for piece in provider.stream_chat(
                    [{"role": "user", "content": "test"}], [], "request"
                )
            ]
        )

    assert asyncio.run(collect()) == "你好"
    assert captured[0]["stream"] is True


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False)])
def test_deepseek_http_failures(settings, status, retryable):
    async def collect():
        provider = DeepSeekProvider(settings, httpx.MockTransport(lambda _: httpx.Response(status)))
        return [piece async for piece in provider.stream_chat([], [], "request")]

    with pytest.raises(ProviderFailure) as result:
        asyncio.run(collect())
    assert result.value.retryable is retryable


def test_config_resolves_from_project_not_cwd(tmp_path, monkeypatch):
    from app.settings import ROOT

    env = tmp_path / "config.env"
    env.write_text(
        "JWT_SECRET="
        + "a" * 40
        + "\nDATA_DIR=./artifacts/config-test\nDATABASE_URL=sqlite:///./artifacts/config-test/app.db\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings.load(env)
    assert settings.data_dir == ROOT / "artifacts/config-test"
