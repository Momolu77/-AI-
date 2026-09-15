"""
应用入口 - 通义千问版本

启动命令：
    uvicorn main:app --reload

特性：
- SQLite 数据库自动初始化
- CORS 跨域支持
- WebSocket 实时通信
- 内存缓存（替代 Redis）
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api import session_router, websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    print("✅ 数据库初始化完成")
    print(f"✅ 使用模型: 主对话={settings.chat_model}, 判断={settings.judge_model}")
    print(f"✅ 上下文限制: {settings.max_context_tokens} tokens")
    yield
    # 关闭时清理资源
    print("👋 应用已关闭")


app = FastAPI(
    title="元认知自适应学习系统",
    description="基于生成式AI的实时元认知状态识别与自适应干预系统",
    version="2.0.0-qwen",
    lifespan=lifespan
)

# CORS 配置
origins = settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(session_router, prefix="/api/sessions", tags=["Session"])
app.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])


@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "version": "2.0.0-qwen",
        "chat_model": settings.chat_model,
        "judge_model": settings.judge_model,
        "database": "SQLite",
        "cache": "Memory"
    }


@app.get("/health")
async def health():
    """健康检查（Kubernetes/Docker 专用）"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development")
    )
