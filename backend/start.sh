#!/usr/bin/env bash
# 快速启动脚本（开发环境）

set -e

cd "$(dirname "$0")"

# 1. 创建虚拟环境（如未存在）
if [ ! -d ".venv" ]; then
    python -m venv .venv
fi

# 2. 激活虚拟环境
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt -q

# 4. 复制 .env（如未存在）
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[!] 已创建 .env，请填写 ANTHROPIC_API_KEY 和数据库配置"
fi

# 5. 启动
uvicorn main:app --reload --host 0.0.0.0 --port 8000
