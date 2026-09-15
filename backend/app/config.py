"""
应用配置模块 - 通义千问版本

使用 Pydantic Settings 加载环境变量，支持：
- .env 文件自动加载
- 环境变量覆盖
- 类型校验和默认值

通义千问版本特点：
- 使用阿里云百炼 API (OpenAI 兼容接口)
- 主对话使用 qwen3.8-flash (流式输出)
- 判断任务使用 qwen3.7-flash (结构化输出)
- 数据库默认为 SQLite
- 使用内存缓存替代 Redis
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类"""

    # ═══════════════════════════════════════════════════════
    # 数据库配置（SQLite 默认）
    # ═══════════════════════════════════════════════════════
    database_url: str = "sqlite+aiosqlite:///./metacog.db"

    # Redis配置（保留字段，但实际使用内存缓存）
    redis_url: str = "redis://localhost:6379/0"

    # ═══════════════════════════════════════════════════════
    # 阿里云百炼 API 配置
    # ═══════════════════════════════════════════════════════
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 模型配置
    chat_model: str = "qwen3.8-flash"  # 主对话模型
    judge_model: str = "qwen3.7-flash"  # 判断任务模型（结构化输出）

    # 上下文配置
    max_context_tokens: int = 24000  # 限制到 24K (留余量)

    # ═══════════════════════════════════════════════════════
    # 应用配置
    # ═══════════════════════════════════════════════════════
    # 安全配置
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60

    # CORS配置
    cors_origins: list[str] | str = ["http://localhost:5173"]

    # 服务器配置
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # 日志配置
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
