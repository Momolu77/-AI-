# 🚀 系统启动步骤（已配置 API Key 版本）

## 当前状态
✅ API Key 已填写到 `.env` 文件  
✅ 代码已迁移到通义千问版本  
✅ 测试脚本已准备完毕

---

## 第一步：测试 API 连接（2分钟）

打开命令行，运行：

```bash
cd backend
python test_qwen.py
```

**预期输出**：
```
🧪 通义千问 API 测试

============================================================
测试 1: 主对话接口 (qwen3.8-flash)
============================================================
发送消息: 你好，请用一句话介绍你自己

✅ API 调用成功
回复: 我是通义千问，一个由阿里云开发的大语言模型...

Token 用量:
  - 输入: 10 tokens
  - 输出: 25 tokens
  - 总计: 35 tokens

============================================================
测试 2: 流式输出 (qwen3.8-flash)
============================================================
发送消息: 用三个词描述春天
回复: 生机、温暖、希望

✅ 流式输出测试成功

============================================================
测试 3: 判断模型 (qwen3.7-flash)
============================================================
发送消息: 判断情感（积极/消极）：'今天天气真好'

✅ 判断模型调用成功
回复: 积极

============================================================
测试结果汇总
============================================================
✅ 主对话接口
✅ 流式输出
✅ 判断模型

🎉 所有测试通过！API 配置正确
```

**如果测试失败**，查看错误信息并检查：
1. API Key 是否正确填写
2. 账户余额是否充足
3. 网络连接是否正常

---

## 第二步：运行完整环境检查（1分钟）

```bash
python check_env.py
```

**预期输出**：
```
🔍 元认知自适应学习系统 - 环境检查

==================================================
1. 检查 Python 版本
==================================================
当前 Python 版本: 3.11.x
✅ Python 版本符合要求 (>= 3.11)

==================================================
2. 检查依赖包
==================================================
✅ fastapi
✅ uvicorn
✅ sqlalchemy
✅ aiosqlite
✅ pydantic
✅ openai
✅ numpy
✅ pandas

✅ 所有依赖包已安装

==================================================
3. 检查环境变量文件
==================================================
✅ .env 文件存在

==================================================
4. 检查 API Key 配置
==================================================
✅ DASHSCOPE_API_KEY 已配置: sk-xxxxxxx... (长度: 64)

==================================================
5. 测试阿里云百炼 API 连接
==================================================
正在测试 API 连接...
✅ API 连接成功
模型: qwen3.8-flash
测试回复: 你好！

==================================================
6. 检查数据库配置
==================================================
数据库 URL: sqlite+aiosqlite:///./metacog.db
✅ 使用 SQLite 数据库（无需额外配置）
ℹ️  数据库文件将在首次启动时自动创建: ./metacog.db

==================================================
检查结果汇总
==================================================
✅ Python 版本
✅ 依赖包
✅ 环境变量文件
✅ API Key 配置
✅ API 连接测试
✅ 数据库配置

🎉 环境检查通过！

下一步:
1. 启动后端: uvicorn main:app --reload
2. 启动前端: cd ../frontend && npm run dev
3. 访问: http://localhost:5173
```

---

## 第三步：启动后端（保持运行）

```bash
uvicorn main:app --reload
```

**预期输出**：
```
✅ 数据库初始化完成
✅ 使用模型: 主对话=qwen3.8-flash, 判断=qwen3.7-flash
✅ 上下文限制: 24000 tokens
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**验证后端是否正常**：
- 访问 http://localhost:8000 应该看到：
  ```json
  {
    "status": "ok",
    "version": "2.0.0-qwen",
    "chat_model": "qwen3.8-flash",
    "judge_model": "qwen3.7-flash",
    "database": "SQLite",
    "cache": "Memory"
  }
  ```

- 访问 http://localhost:8000/docs 查看 API 文档

---

## 第四步：启动前端（新终端）

**打开新的命令行窗口**，运行：

```bash
cd frontend
npm run dev
```

**预期输出**：
```
VITE v5.x.x  ready in 500 ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
➜  press h + enter to show help
```

---

## 第五步：测试完整流程（5分钟）

### 5.1 打开浏览器

访问：http://localhost:5173

### 5.2 创建会话

1. **用户ID**：输入 `202520700524`（或任意学号）
2. **任务类型**：选择 `写作任务`
3. **任务描述**：输入 `写一篇关于人工智能的短文`
4. 点击 **开始学习会话**

### 5.3 测试对话

**测试1：基本对话**
- 输入：`你好，我需要写一篇关于AI的文章，但不知道从哪里开始`
- 观察：
  - ✅ AI 回复逐字显示（流式输出）
  - ✅ 右侧状态面板显示 Planning 分数上升
  - ✅ 可能触发 "planning_low" 干预提示

**测试2：多轮对话**
- 输入：`AI有哪些应用领域？`
- 输入：`机器学习和深度学习有什么区别？`
- 输入：`我的文章应该怎么组织结构？`
- 观察：
  - ✅ 状态曲线动态变化
  - ✅ Planning、Monitoring、Evaluation 三维度分数实时更新

**测试3：触发干预**
- 连续提问 5 次简单问题（例如：`好的`、`知道了`、`还有呢`）
- 观察：
  - ✅ Monitoring 或 Evaluation 分数下降
  - ✅ 可能触发干预提示卡片

### 5.4 检查数据持久化

刷新页面或断开重连，对话历史应该保留。

---

## 🎯 系统功能清单

测试完成后，确认以下功能正常：

- [ ] 创建会话成功
- [ ] AI 流式回复正常
- [ ] 状态面板实时更新（Planning / Monitoring / Evaluation）
- [ ] 状态曲线动态绘制
- [ ] 干预提示正常触发
- [ ] 刷新页面后对话历史保留
- [ ] 后端日志无异常

---

## 🐛 常见问题排查

### 问题1：`test_qwen.py` 报错 "❌ API 调用失败"

**可能原因**：
1. API Key 填写错误
2. 余额不足
3. 网络问题

**解决方法**：
1. 打开 `.env`，确认 `DASHSCOPE_API_KEY=sk-...` 格式正确
2. 访问 https://bailian.console.aliyun.com/ 检查余额
3. 测试网络：`curl https://dashscope.aliyuncs.com`

### 问题2：`check_env.py` 报错 "❌ 缺少依赖包"

**解决方法**：
```bash
pip install -r requirements.txt
```

### 问题3：启动后端报错 "ModuleNotFoundError"

**解决方法**：
```bash
# 确保虚拟环境已激活
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# 重新安装依赖
pip install -r requirements.txt
```

### 问题4：前端显示 "创建会话失败"

**检查后端是否运行**：
```bash
curl http://localhost:8000
```

应该返回 JSON 数据。如果无响应，说明后端未启动。

### 问题5：AI 不回复或回复很慢

**检查后端日志**，查看是否有报错。可能原因：
1. API 请求超时（网络问题）
2. 模型名称错误
3. Token 用量超限

---

## 📊 数据库查看

系统运行后，会在 `backend/` 目录下生成 `metacog.db` 文件。

使用 SQLite 工具查看数据：

**推荐工具**：
- DB Browser for SQLite: https://sqlitebrowser.org/
- VSCode 插件: SQLite Viewer

**主要表**：
- `sessions`: 学习会话
- `interaction_logs`: 对话记录（含 AI 消息）
- `metacog_states`: 元认知状态快照
- `interventions`: 干预记录

---

## 🎓 下一步探索

系统启动成功后，可以：

1. **修改 AI 提示词**：编辑 `backend/app/services/ai_generator.py`
2. **调整状态识别算法**：编辑 `backend/app/services/state_recognizer.py`
3. **自定义干预规则**：编辑 `backend/app/services/intervention.py`
4. **修改前端 UI**：编辑 `frontend/src/components/`

---

## 📮 获取帮助

遇到问题时：
1. 查看后端日志（运行 `uvicorn` 的终端）
2. 查看浏览器控制台（F12 → Console）
3. 查看 `MIGRATION_SUMMARY.md` 了解系统改动
4. 提交 Issue 并附上错误日志

---

**文档版本**: v2.0.0-qwen  
**最后更新**: 2026-09-14
