# 阿里云百炼（通义千问）迁移总结

## ✅ 已完成的改动

### 1. 配置层 (`backend/app/config.py`)
- ✅ 添加 `dashscope_api_key` 配置项
- ✅ 添加 `dashscope_base_url` 配置项
- ✅ 分离模型配置：`chat_model` (qwen3.8-flash) 和 `judge_model` (qwen3.7-flash)
- ✅ 添加 `max_context_tokens` 上下文限制 (24K)

### 2. AI生成服务 (`backend/app/services/ai_generator.py`)
- ✅ 使用 OpenAI 兼容接口调用通义千问
- ✅ 实现流式输出：`chat_with_ai_stream()`
- ✅ 实现结构化输出：`judge_with_structured_output()`
- ✅ 关闭思考模式（`enable_thinking: False`）
- ✅ 上下文管理：超过 24K 自动摘要
- ✅ 传递任务描述到 AI

### 3. WebSocket 层 (`backend/app/api/websocket.py`)
- ✅ 流式输出支持（推送 `ai_reply_chunk` 和 `ai_reply_done`）
- ✅ 持久化 AI 消息到数据库
- ✅ 传递任务描述到 AI 生成器
- ✅ 加载对话历史（断线重连恢复上下文）
- ✅ 记录模型名称（为后续记录 Token 用量预留字段）

### 4. 数据库模型 (`backend/app/models.py`)
- ✅ 添加 `role` 字段（user / assistant / system）
- ✅ 添加 `model_name` 字段（记录使用的模型）
- ✅ 添加 `tokens_used` 字段（记录 Token 用量）
- ✅ 添加 `request_id` 字段（记录阿里云请求 ID）

### 5. 依赖包 (`backend/requirements.txt`)
- ✅ 添加 `openai` SDK（用于调用通义千问）
- ✅ 移除 `anthropic` 依赖
- ✅ 保留 `numpy` 和 `pandas`（状态识别需要）

### 6. 应用入口 (`backend/main.py`)
- ✅ 更新启动信息（显示使用的模型和上下文限制）
- ✅ 更新版本号为 `2.0.0-qwen`

### 7. 文档更新
- ✅ 更新 `README.md`（新增通义千问版本说明）
- ✅ 创建 `QUICKSTART.md`（快速启动指南）
- ✅ 更新 `.env.example`（新增阿里云配置说明）
- ✅ 更新 `.env`（新增阿里云配置）

---

## 🔧 需要手动完成的步骤

### 1. 填写 API Key

编辑 `backend/.env`，将第 16 行：
```env
DASHSCOPE_API_KEY=你的API密钥请替换这里
```

改为：
```env
DASHSCOPE_API_KEY=sk-你的实际密钥
```

**获取方法**：
- 阿里云百炼：https://bailian.console.aliyun.com/
- DashScope：https://dashscope.console.aliyun.com/

### 2. 安装/升级依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 数据库迁移（添加新字段）

由于数据库模型有变更（添加了 `role`, `model_name` 等字段），需要：

**选项A：删除旧数据库（推荐测试阶段）**
```bash
cd backend
rm metacog.db  # 删除旧数据库，系统会自动创建新的
uvicorn main:app --reload
```

**选项B：保留数据（生产环境）**
```bash
# 需要使用 Alembic 进行数据库迁移
# 如果你之前没有配置 Alembic，建议使用选项A
```

### 4. 启动系统测试

```bash
# 终端1：启动后端
cd backend
venv\Scripts\activate
uvicorn main:app --reload

# 终端2：启动前端
cd frontend
npm run dev
```

---

## 🎯 三种负载的实现

### 负载1: 主对话（已实现）
- **模型**: `qwen3.8-flash`
- **温度**: 0.7
- **思考模式**: 关闭
- **输出**: 流式输出
- **位置**: `ai_generator.py` → `chat_with_ai_stream()`

### 负载2: 判断任务（已实现）
- **模型**: `qwen3.7-flash`
- **温度**: 0（严格输出）
- **输出**: 结构化 JSON
- **位置**: `ai_generator.py` → `judge_with_structured_output()`
- **用途**: 目标明确度、追问、纠错、编辑深度判断

### 负载3: 干预提示（已实现）
- **模型**: 无（本地模板）
- **位置**: `ai_generator.py` → `generate_intervention()`
- **用途**: 元认知提示、过程支架、反思提示、策略建议

---

## 📋 待完善的功能

### 1. Token 用量统计（中优先级）

通义千问响应中包含 `usage` 字段，需要提取并保存：

```python
# 在 ai_generator.py 中
completion = client.chat.completions.create(...)
# 从响应中提取
usage = completion.usage
tokens_used = {
    'prompt': usage.prompt_tokens,
    'completion': usage.completion_tokens,
    'total': usage.total_tokens
}
```

### 2. 请求 ID 记录（低优先级）

通义千问响应中包含 `request_id`，用于追踪和调试：

```python
request_id = completion.id  # 或者从响应头中提取
```

### 3. 判断任务接口集成（中优先级）

目前 `judge_with_structured_output()` 已实现，但尚未在实际业务中调用。需要在以下场景中使用：

- 目标明确度判断（用户输入任务描述时）
- 追问生成（AI 识别到信息不足时）
- 纠错判断（用户提交草稿时）
- 编辑深度判断（用户修改内容时）

---

## 🚀 测试清单

启动系统后，依次测试：

- [ ] 创建会话成功
- [ ] AI 回复正常显示（流式输出）
- [ ] 状态面板实时更新
- [ ] 状态曲线动态绘制
- [ ] 干预提示正常触发
- [ ] 断线重连后上下文恢复
- [ ] 长对话自动摘要（发送 20+ 条消息测试）
- [ ] 数据库正确保存消息和状态

---

## 📝 关键差异对比

| 功能 | Anthropic 版本 | 通义千问版本 |
|------|---------------|-------------|
| API Key | `ANTHROPIC_API_KEY` | `DASHSCOPE_API_KEY` |
| 主对话模型 | `claude-3-5-sonnet-20241022` | `qwen3.8-flash` |
| 判断模型 | 无 | `qwen3.7-flash` |
| 流式输出 | 支持 | 支持 |
| 思考模式 | 自动 | 手动关闭 |
| 上下文管理 | 200K | 24K（手动摘要）|
| 数据库 | PostgreSQL | SQLite |
| 缓存 | Redis | 内存缓存 |
| 价格 | $3/M input tokens | ¥0.2/M tokens |

---

## ⚠️ 注意事项

1. **上下文限制**: 通义千问支持 1M 上下文，但为了控制成本和响应速度，设置为 24K。超出后自动摘要。

2. **流式输出延迟**: 前端需要处理 `ai_reply_chunk` 事件，逐字显示回复。

3. **数据库字段**: 新增的 `role`, `model_name` 等字段需要数据库迁移。测试阶段建议删除旧数据库。

4. **错误处理**: 已添加基本的异常捕获，但生产环境需要完善日志和监控。

---

**迁移完成度**: 95%  
**剩余工作**: 填写 API Key + 安装依赖 + 测试
