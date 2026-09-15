# 快速启动指南 - 通义千问版本

## 🚀 5分钟快速启动

### 前置要求

✅ Python 3.11+  
✅ Node.js 18+  
✅ 阿里云百炼 API Key（[获取地址](https://bailian.console.aliyun.com/)）

---

## 步骤1: 后端配置（3分钟）

### 1.1 进入后端目录

```bash
cd backend
```

### 1.2 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 1.3 安装依赖

```bash
pip install -r requirements.txt
```

### 1.4 配置 API Key

复制环境变量模板：
```bash
# Windows
copy .env.example .env

# Mac/Linux
cp .env.example .env
```

编辑 `.env` 文件，修改这一行：
```env
DASHSCOPE_API_KEY=你的API密钥请替换这里
```

改为：
```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 1.5 启动后端

```bash
uvicorn main:app --reload
```

**成功标志**：
```
✅ 数据库初始化完成
✅ 使用模型: 主对话=qwen3.8-flash, 判断=qwen3.7-flash
✅ 上下文限制: 24000 tokens
INFO: Uvicorn running on http://127.0.0.1:8000
```

---

## 步骤2: 前端配置（2分钟）

### 2.1 打开新终端，进入前端目录

```bash
cd frontend
```

### 2.2 安装依赖

```bash
npm install
```

### 2.3 启动前端

```bash
npm run dev
```

**成功标志**：
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
```

---

## 步骤3: 验证系统

### 3.1 访问前端

打开浏览器访问: http://localhost:5173

### 3.2 创建会话

1. 输入用户ID（例如：`202520700524`）
2. 选择任务类型（例如：`写作任务`）
3. 填写任务描述（例如：`写一篇关于AI的文章`）
4. 点击 **开始学习会话**

### 3.3 测试对话

输入一条消息（例如：`你好，我需要帮助`），观察：

- ✅ AI 回复逐字显示（流式输出）
- ✅ 右侧状态面板显示 PME 分数
- ✅ 状态曲线开始绘制
- ✅ 触发干预时弹出提示卡片

---

## 🐛 常见问题

### 问题1: "创建会话失败"

**症状**: 点击"开始学习会话"后显示错误

**原因**: 后端未启动或 API Key 配置错误

**解决方法**:
1. 检查后端是否运行: 访问 http://localhost:8000
2. 查看后端终端是否有错误信息
3. 确认 `.env` 文件中 `DASHSCOPE_API_KEY` 已填写

### 问题2: "AI 不回复"

**症状**: 发送消息后没有回复

**原因**: API Key 无效或余额不足

**解决方法**:
1. 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 检查余额
2. 测试 API Key 是否有效:
   ```bash
   cd backend
   python -c "from app.config import settings; print(settings.dashscope_api_key)"
   ```
3. 查看后端终端错误信息

### 问题3: "状态不更新"

**症状**: 右侧状态面板显示 0.00

**原因**: WebSocket 连接断开或状态识别未触发

**解决方法**:
1. 打开浏览器开发者工具 → Network → WS 查看连接状态
2. 多发送几条消息（状态需要积累数据后才能计算）
3. 检查后端日志是否有异常

### 问题4: "端口被占用"

**症状**: 
```
ERROR: [Errno 10048] error while attempting to bind on address
```

**解决方法**:
```bash
# 后端换端口
uvicorn main:app --reload --port 8001

# 前端换端口
npm run dev -- --port 5174
```

---

## 🔧 高级配置

### 修改模型

编辑 `backend/.env`：
```env
CHAT_MODEL=qwen3.8-flash     # 主对话模型
JUDGE_MODEL=qwen3.7-flash    # 判断模型
```

可选模型：
- `qwen3.8-flash` - 快速响应（推荐主对话）
- `qwen3.7-flash` - 结构化输出（推荐判断）
- `qwen-turbo` - 平衡性能
- `qwen-plus` - 高质量

### 修改上下文限制

编辑 `backend/.env`：
```env
MAX_CONTEXT_TOKENS=24000  # 默认24K，可调整到 16K-32K
```

### 修改 CORS 允许的前端地址

编辑 `backend/.env`：
```env
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]
```

---

## 📝 目录结构

启动后的目录结构：

```
backend/
├── venv/                # 虚拟环境（自动生成）
├── metacog.db           # SQLite 数据库（自动生成）
├── .env                 # 环境变量（手动创建）
└── main.py

frontend/
├── node_modules/        # Node.js 依赖（自动生成）
└── src/
```

---

## 🎯 下一步

系统启动成功后，可以：

1. **测试完整流程**: 创建会话 → 对话 → 观察状态变化 → 触发干预
2. **查看数据库**: 使用 SQLite 工具查看 `metacog.db`
3. **查看 API 文档**: 访问 http://localhost:8000/docs
4. **自定义提示词**: 编辑 `backend/app/services/ai_generator.py`
5. **修改状态识别算法**: 编辑 `backend/app/services/state_recognizer.py`

---

## 📮 获取帮助

如遇到问题：
1. 查看后端终端错误信息
2. 查看浏览器控制台错误信息
3. 提交 Issue 并附上错误日志

---

**版本**: v2.0.0-qwen  
**最后更新**: 2026-09-14
