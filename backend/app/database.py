from typing import Optional, Dict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ═══════════════════════════════════════════════════════════
# SQLite 数据库配置
# ═══════════════════════════════════════════════════════════

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 特殊配置
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# ═══════════════════════════════════════════════════════════
# 内存缓存（替代 Redis）
# ═══════════════════════════════════════════════════════════

# 全局状态缓存（字典结构）
_state_cache: Dict[str, dict] = {}


async def get_state_cache(session_id: str) -> Optional[dict]:
    """
    从内存缓存中获取状态

    Args:
        session_id: 会话ID

    Returns:
        状态字典 或 None
    """
    return _state_cache.get(session_id)


async def set_state_cache(session_id: str, state: dict, ttl: int = 3600) -> None:
    """
    将状态保存到内存缓存

    Args:
        session_id: 会话ID
        state: 状态字典
        ttl: 过期时间（秒）- 内存版本忽略此参数

    Note:
        内存缓存在服务重启后会丢失，但不影响核心功能
        状态会从数据库重新计算
    """
    _state_cache[session_id] = state


async def clear_state_cache(session_id: str) -> None:
    """
    清除指定会话的缓存

    Args:
        session_id: 会话ID
    """
    if session_id in _state_cache:
        del _state_cache[session_id]
