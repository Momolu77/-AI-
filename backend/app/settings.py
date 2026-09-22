import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path
    database: Path
    secret: str
    env: str = "local"
    task_id: str = "task-test"
    ai_provider: str = "fake"
    fake_scenario: str = "success"
    ai_concurrency: int = 2
    connect_timeout: float = 10
    first_token_timeout: float = 30
    total_timeout: float = 120
    max_output: int = 100000
    deepseek_key: str = ""
    deepseek_model: str = "deepseek-chat"
    heartbeat: int = 15
    session_timeout: int = 1800
    attachment_max: int = 10485760
    attachment_types: str = ".txt,.md,.html,.pdf,.docx"
    code_max: int = 1048576

    @classmethod
    def load(cls, env_file: str | Path = ROOT / ".env.local"):
        values = {**dotenv_values(env_file), **os.environ}

        def path(value):
            p = Path(value)
            return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()

        data = path(values.get("DATA_DIR", "./data/local"))
        db = path(
            values.get("DATABASE_URL", f"sqlite:///{data / 'app.db'}").removeprefix("sqlite:///")
        )
        settings = cls(
            data_dir=data,
            database=db,
            secret=values.get("JWT_SECRET", ""),
            env=values.get("APP_ENV", "local"),
            task_id=values.get("TASK_ID", "task-test"),
            ai_provider=values.get("AI_PROVIDER", "fake"),
            fake_scenario=values.get("FAKE_AI_SCENARIO", "success"),
            ai_concurrency=int(values.get("AI_MAX_CONCURRENCY", 2)),
            connect_timeout=float(values.get("AI_CONNECT_TIMEOUT_SEC", 10)),
            first_token_timeout=float(values.get("AI_FIRST_TOKEN_TIMEOUT_SEC", 30)),
            total_timeout=float(values.get("AI_TOTAL_TIMEOUT_SEC", 120)),
            max_output=int(values.get("AI_MAX_OUTPUT_CHARS", 100000)),
            deepseek_key=values.get("DEEPSEEK_API_KEY", ""),
            deepseek_model=values.get("DEEPSEEK_MODEL", "deepseek-chat"),
            heartbeat=int(values.get("HEARTBEAT_INTERVAL_SEC", 15)),
            session_timeout=int(values.get("SESSION_TIMEOUT_SEC", 1800)),
            attachment_max=int(values.get("ATTACHMENT_MAX_BYTES", 10485760)),
            attachment_types=values.get("ATTACHMENT_TYPES", ".txt,.md,.html,.pdf,.docx"),
            code_max=int(values.get("CODE_MAX_BYTES", 1048576)),
        )
        if len(settings.secret) < 32:
            raise ValueError("JWT_SECRET 至少 32 字符。请先运行 scripts/local_init.py。")
        if settings.env == "test" and (
            data.is_relative_to((ROOT / "data/local").resolve())
            or db.is_relative_to((ROOT / "data/local").resolve())
        ):
            raise ValueError("自动测试不得使用 data/local")
        if settings.ai_provider not in {"fake", "deepseek"}:
            raise ValueError("AI_PROVIDER 只能为 fake 或 deepseek")
        if settings.ai_provider == "deepseek" and not settings.deepseek_key:
            raise ValueError("DeepSeek 模式需要 DEEPSEEK_API_KEY")
        if min(settings.ai_concurrency, settings.session_timeout, settings.heartbeat) < 1:
            raise ValueError("并发、心跳与超时配置必须为正数")
        return settings
