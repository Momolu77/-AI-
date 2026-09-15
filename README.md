# 元认知自适应学习系统

> 基于学习过程日志的元认知状态识别与生成式AI自适应干预系统

## 🎯 系统概述

本系统通过实时采集人-AI协作学习过程中的交互数据（对话记录、Prompt行为、修改轨迹等），识别学习者的元认知状态（Planning、Monitoring、Evaluation），并根据状态动态生成个性化干预提示，支持学习者的自我调节学习过程。

### 核心功能

- **实时交互采集**: WebSocket 实时记录对话、prompt、修改等学习行为
- **元认知状态识别**: 基于行为特征计算 Planning/Monitoring/Evaluation 三维状态向量
- **自适应干预决策**: 根据状态变化趋势触发干预（低水平检测、波动检测、策略建议）
- **生成式AI响应**: 调用阿里云百炼通义千问 API 生成情境化对话和结构化判断
- **可视化分析**: 实时展示状态曲线、干预历史和交互日志

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────┐
│           前端 (React + TypeScript)          │
│   - ChatInterface (对话界面)                 │
│   - StateVisualization (状态可视化)          │
│   - WebSocket Client (实时通信)              │
└──────────────┬──────────────────────────────┘
               │ HTTP/WebSocket
┌──────────────┴──────────────────────────────┐
│         后端 (FastAPI + Python)              │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  API Layer                          │    │
│  │  - /api/sessions (会话管理)         │    │
│  │  - /ws/session/{id} (WebSocket)     │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Service Layer                      │    │
│  │  - state_recognizer.py (状态识别)   │    │
│  │  - intervention.py (干预决策)       │    │
│  │  - ai_generator.py (AI生成)         │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  Data Layer                         │    │
│  │  - SQLite (持久化存储)              │    │
│  │  - Memory Cache (状态缓存)          │    │
│  └─────────────────────────────────────┘    │
└──────────────┬──────────────────────────────┘
               │
       阿里云百炼 API (通义千问)
```

## 🚀 快速开始

### 前置要求

- Node.js >= 18.0
- Python >= 3.11
- 阿里云百炼 API Key（通义千问）

### 1. 克隆项目

```bash
git clone <repository-url>
cd 9.13毕业系统
```

### 2. 后端配置

```bash
cd backend

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Mac/Linux: source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env  # Mac/Linux: cp .env.example .env
# 编辑 .env 填入阿里云百炼 API Key

# 启动服务
uvicorn main:app --reload
```

**获取 API Key**: 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 或 [DashScope](https://dashscope.console.aliyun.com/)

后端运行在 `http://localhost:8000`

### 3. 前端配置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:5173`

### 4. 验证系统

访问 `http://localhost:5173`，创建一个学习会话并开始对话，观察：
- ✅ AI正常回复（流式输出）
- ✅ 右侧状态面板实时更新
- ✅ 状态曲线动态绘制
- ✅ 触发干预时显示提示卡片

## 📁 项目结构

```
.
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/               # API路由
│   │   │   ├── sessions.py    # 会话管理接口
│   │   │   └── websocket.py   # WebSocket接口
│   │   ├── models.py          # 数据库模型
│   │   ├── schemas.py         # Pydantic数据模型
│   │   ├── services/          # 核心服务
│   │   │   ├── state_recognizer.py   # 元认知状态识别
│   │   │   ├── intervention.py       # 干预决策引擎
│   │   │   └── ai_generator.py       # AI内容生成
│   │   ├── database.py        # 数据库连接
│   │   ├── redis_client.py    # 内存缓存
│   │   └── config.py          # 配置管理
│   ├── main.py                # FastAPI入口
│   ├── requirements.txt       # Python依赖
│   └── .env.example           # 环境变量模板
│
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── components/        # React组件
│   │   │   ├── ChatInterface.tsx
│   │   │   └── StateVisualization.tsx
│   │   ├── hooks/             # 自定义Hooks
│   │   │   └── useWebSocket.ts
│   │   ├── pages/             # 页面
│   │   │   ├── HomePage.tsx
│   │   │   └── SessionPage.tsx
│   │   ├── types/             # TypeScript类型
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
└── README.md                   # 本文档
```

## 🔧 核心模块说明

### 状态识别 (`state_recognizer.py`)

基于交互行为特征提取，计算三维元认知状态向量：

```python
state = {
    "planning": 0.0 - 1.0,      # 计划性（prompt长度、问题复杂度）
    "monitoring": 0.0 - 1.0,    # 监控性（编辑频率、验证行为）
    "evaluation": 0.0 - 1.0     # 评价性（反思性语言、自我评估）
}
```

### 干预决策 (`intervention.py`)

三类干预触发条件：

1. **低水平干预**: 某维度持续低于阈值
2. **波动干预**: 状态剧烈变化
3. **策略建议**: 基于当前状态推荐学习策略

### AI生成 (`ai_generator.py`)

**通义千问版本特性**：

- **主对话**: 使用 `qwen3.8-flash` 流式生成（关闭思考模式）
- **判断任务**: 使用 `qwen3.7-flash` 结构化输出（温度=0）
- **上下文管理**: 限制到 24K tokens，超出后自动摘要
- **持久化**: 记录模型版本、Token用量、请求ID

三种负载分离：
1. 主对话回复 → `qwen3.8-flash`
2. 目标明确度、追问、纠错判断 → `qwen3.7-flash`
3. 干预提示 → 本地模板

## 📊 数据库设计

### 核心表

- **sessions**: 学习会话（用户ID、任务类型、任务描述）
- **interaction_logs**: 交互日志（消息内容、角色、模型名、Token用量）
- **metacog_states**: 元认知状态快照（PME分数、置信度）
- **interventions**: 干预记录（类型、触发原因、内容）

详见 `backend/app/models.py`

## 🔌 API文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要接口

```
POST   /api/sessions              创建新会话
GET    /api/sessions/{id}         获取会话详情
WS     /ws/session/{id}           WebSocket连接（实时通信）
```

### WebSocket消息格式

**客户端 → 服务端**
```json
{
  "event_type": "prompt",
  "content": "用户输入的内容"
}
```

**服务端 → 客户端（新增流式输出）**
```json
{
  "type": "ai_reply_chunk",  // 流式输出片段
  "data": {"content": "生成的文本片段"}
}

{
  "type": "ai_reply_done",   // 完整回复
  "data": {"content": "完整的回复内容"}
}

{
  "type": "state_update",    // 状态更新
  "data": {
    "planning": 0.65,
    "monitoring": 0.42,
    "evaluation": 0.0
  }
}

{
  "type": "intervention",    // 干预提示
  "data": {
    "type": "planning_low",
    "reason": "规划维度持续低于阈值",
    "content": "建议先明确写作目标..."
  }
}
```

## 🧪 测试

### 后端测试
```bash
cd backend
pytest
```

### 前端测试
```bash
cd frontend
npm test
```

## 📝 开发指南

### 添加新的元认知特征

1. 在 `state_recognizer.py` 的 `extract_features()` 中添加特征提取逻辑
2. 在 `compute_metacog_state()` 中更新状态计算公式
3. 更新 `MetacogState` 模型（如需持久化新字段）

### 添加新的干预类型

1. 在 `intervention.py` 中定义新的触发条件
2. 在 `ai_generator.py` 中添加对应的模板
3. 前端 `StateVisualization.tsx` 添加UI展示逻辑

### 自定义AI提示词

编辑 `ai_generator.py` 中的 `SYSTEM_PROMPT` 和各干预类型的提示模板。

## 🐛 故障排查

### 问题1: "创建会话失败"

**原因**: 后端未启动或 `.env` 配置错误

**解决**:
1. 检查后端是否运行: 访问 http://localhost:8000
2. 检查 `.env` 文件中 `DASHSCOPE_API_KEY` 是否填写

### 问题2: AI不回复

**原因**: API Key 无效或余额不足

**解决**:
1. 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 检查余额
2. 重新生成 API Key 并更新 `.env`

### 问题3: 状态不更新

**原因**: WebSocket 连接断开

**解决**:
1. 打开浏览器开发者工具 → Network → WS 查看连接状态
2. 重启前端: `npm run dev`

## 🔄 版本历史

### v2.0.0-qwen (2026-09-14)
- ✨ 迁移到阿里云百炼（通义千问）
- ✨ 新增流式输出支持
- ✨ 上下文管理（24K tokens限制 + 自动摘要）
- ✨ 持久化 AI 消息和元数据
- ✨ 分离三种负载（主对话/判断/干预）
- 🗑️ 移除 PostgreSQL 和 Redis 依赖
- 📝 使用 SQLite + 内存缓存

### v1.0.0 (2026-09-13)
- 🎉 初始版本
- ✅ Anthropic Claude 集成
- ✅ 元认知状态识别
- ✅ 自适应干预决策

## 📄 许可证

本项目仅用于学术研究和毕业设计，未经授权不得用于商业用途。

## 👥 贡献者

- 开发者: [Your Name]
- 指导教师: [Advisor Name]

## 📮 联系方式

如有问题或建议，请提交 Issue 或联系: [your-email@example.com]

---

**系统版本**: v2.0.0-qwen  
**最后更新**: 2026-09-14
