"""
内存缓存客户端（替代 Redis）

使用 Python 字典作为内存缓存，无需安装 Redis
"""

from typing import Optional, Dict
from app.database import get_state_cache, set_state_cache, clear_state_cache


async def get_redis():
    """
    返回内存缓存接口（兼容 Redis 接口）

    Returns:
        MemoryCacheClient: 内存缓存客户端
    """
    return MemoryCacheClient()


class MemoryCacheClient:
    """
    内存缓存客户端，模拟 Redis 接口
    """

    async def get(self, key: str) -> Optional[str]:
        """获取缓存值"""
        state = await get_state_cache(key)
        if state is None:
            return None

        # 返回 JSON 字符串（模拟 Redis 行为）
        import json
        return json.dumps(state)

    async def set(self, key: str, value: str, ex: int = 3600) -> None:
        """设置缓存值"""
        import json
        state = json.loads(value)
        await set_state_cache(key, state, ttl=ex)

    async def delete(self, key: str) -> None:
        """删除缓存值"""
        await clear_state_cache(key)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        state = await get_state_cache(key)
        return state is not None

