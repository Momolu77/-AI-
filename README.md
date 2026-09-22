# 英语教学资源工作台 · 本地开发版

按 [项目开发文档 v1.1](docs/archive/项目开发文档-v1.1.md) 实现。浏览器完成读题、AI 对话、编辑单文件 HTML、手动运行、记录计划和多次提交；FastAPI 将会话、30 类事件、对话、版本和作品保存在本机 SQLite 与文件目录中。

当前默认使用离线 `fake-local-v1`，不会调用付费 API。原始设计、v1.1 归档和现有 v1.2 文档均保留。实现与验收状态见 [开发清单](docs/development-checklist-v1.1.md) 和 [本轮验收记录](docs/acceptance/local-baseline-2026-09-22.md)。

## 1. 本机启动

本次开发环境：Windows、Python 3.13.11、Node 24.13.0、npm 11.6.2、Microsoft Edge。依赖首次安装需要网络；安装后 fake 模式只使用本地资源。本机不需要 Docker、Redis 或 AI 密钥。

在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
npm --prefix frontend ci
.venv/Scripts/python.exe scripts/local_init.py --env-file .env.local
.venv/Scripts/python.exe scripts/seed_local.py --env-file .env.local
```

`local_init` 仅在密钥为空时生成 JWT 密钥，重复运行不会清库；`seed_local` 重复运行保留三座位的入口。打开其输出的 `http://127.0.0.1:5173/enter?seat=01&token=...`。使用 **127.0.0.1**，不要混用 localhost。

分别在两个终端启动：

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --env-file .env.local --host 127.0.0.1 --port 8000 --reload
```

```powershell
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

也可用 `scripts/start_local.ps1` 在隐藏后台进程中启动两个服务并输出座位入口，再用 `scripts/stop_local.ps1` 停止该脚本启动的进程。重复启动时，如果确认两个端口均属于本脚本记录的进程或其子进程，且健康检查通过，会提示“工作台已在运行”并重新显示座位入口。其他端口占用或服务异常会显示端口/PID 和检查建议。进程日志位于 `artifacts/local-*`。

浏览器刷新恢复当前会话和已持久化草稿；运行中的游戏堆栈不会跨刷新保存，需要手动再运行。任务页与工作区之间切换会保留同一 iframe。主动结束后原会话只读，再次打开座位入口创建新会话。复制同一会话标签页时，Web Locks 阻止重复编辑；模拟不同学生请使用独立 BrowserContext 或不同浏览器配置。

## 2. 已有功能与约定

- 任务页、12 秒本地示例、播放进度恢复、服务器时间校准、只读座位。
- Vue 3、Vuetify、Pinia 三栏工作台；CodeMirror 6 提供 HTML 高亮、查找、撤销和重做。
- 代码本地 800ms 保存、后端每 5 秒检查点；计划 800ms 自动保存。自动保存不会刷新预览。
- 手动运行先冻结并保存代码，成功才替换 iframe。沙箱不启用 same-origin；消息校验 iframe source、run_id、随机通道和数据格式。
- 原始日志、同步异常、Promise 异常、有效点击/选择/提交交互；每次运行显示新的控制台，历史记录保留。
- `.txt/.md/.html/.pdf/.docx` 附件真实解析，默认上限 10 MB。文本需 UTF-8；PDF 必须含可提取文字，扫描件不做 OCR。文件解析失败可重传，不把失败文件送给模型。
- AI 请求排队（全局 2、每会话 1），SSE 显示回复；传输重试沿用请求编号，用户明确重试使用新编号并记录原请求。断流保留片段，订阅不会再次调用模型。
- 提交确认时冻结代码与计划，支持未运行作品、继续编辑、重复传输与多次不可变快照。写盘失败保留草稿；启动恢复 pending 提交、未完成 AI 和附件状态。
- IndexedDB outbox、同步应急日志、逐事件确认、失败队列；30 类契约由服务端验证，系统结果由相应业务服务写入。
- ZIP 内含 JSONL/CSV、任务版本、对话、附件、代码、计划、提交和文件校验；备份恢复至独立目录。

文件扩展名、MIME 和实际格式均会校验；当前没有接入独立杀毒软件。AI 只处理提取文字，不支持图片视觉输入。fake 回复明确标注测试模型，示例词汇不冒充某一真实教材单元。

## 3. 工程结构与接口

```text
backend/app/api/             HTTP 路由、鉴权与 request_id
backend/app/domain/          输入 DTO、30 类事件 schema
backend/app/services/        会话、版本、预览、附件、AI、提交、导出
backend/app/repositories/    SQLite 连接和事务；WAL/外键/忙等待
backend/migrations/         编号 SQL 迁移
backend/tests/              pytest 单元与接口集成
frontend/src/components/    任务页、AI、CodeMirror、控制台和预览
frontend/src/stores/         工作台状态、流程与自动保存
frontend/src/services/      API/SSE、IndexedDB、采集、差分与消息验证
frontend/tests/             Vitest 与 Playwright
config/tasks/               本地任务及锁定内容版本
config/examples/            本地视频，无 CDN
scripts/                    初始化、seed、启动、导出、恢复与核查
data/local/                 手工使用的数据（不入源码仓库）
artifacts/                  自动测试隔离数据、日志、报告与截图
```

主接口 `/api/v1`；Vite 代理 `/api`、`/media` 和 `/health`。鉴权用 Bearer JWT。查看接口及 DTO：http://127.0.0.1:8000/docs 。错误包含 `code/message/retryable/request_id`，响应头也带 `X-Request-ID`。

业务幂等标识在请求体中显式传递：`event_id`、`request_id`、`run_id`、`submission_id`，版本保存使用 revision。重复标识内容不同会拒绝。同一个 HTTP 请求失败重传必须保留标识与原正文。主动重新运行或确认新版本时分配新标识。

AI 创建/重试、预览运行和提交同时支持 `Idempotency-Key` 请求头，其值应与正文中的业务编号相同，前端已自动携带；不一致返回 409。批量事件逐个使用 `event_id` 去重，不以整批 HTTP 请求号代替事件编号。

`sequence_no` 为 **服务器入库顺序**；`client_sequence_no` 保留客户端动作顺序。业务请求、运行、提交依赖各自编号关联。差分位置和 `content_length_after` 用 **UTF-16 code unit**，与 CodeMirror 一致。导出校验使用相同规则，中文和 emoji 可重放。

## 4. 日常测试

命令均从项目根目录执行：

```powershell
.venv/Scripts/python.exe -m ruff check backend scripts
.venv/Scripts/python.exe -m pytest backend/tests/unit backend/tests/integration -q --junitxml=artifacts/backend-results.xml
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit -- --run --reporter=default --reporter=junit --outputFile=../artifacts/frontend-results.xml
npm --prefix frontend run build
npm --prefix frontend run test:e2e
.venv/Scripts/python.exe scripts/audit_e2e.py
```

E2E 默认用已安装的 Microsoft Edge（可设置 `PLAYWRIGHT_CHANNEL=chrome`），独占 **5174/8001**，每轮生成新的 `artifacts/e2e-*` 数据目录，不连接 `data/local`。测试期间关闭 HMR 与服务热重载。测试报告为 `artifacts/playwright-report/index.html`，失败保留截图和 trace。`audit_e2e.py` 应在一轮全部通过的 E2E 后运行一次，逐会话导出、重放编辑差分、核对引用/视频计时，并恢复整个测试库到另一个目录。

故障注入使用测试中的临时目录、网络路由拦截、模拟 provider 和文件写入异常，不耗尽实际磁盘。另提供 `scripts/measure_local.py`，对指定隔离测试入口采样 30 次本地 API 时延。

## 5. 如何逐功能评测

按照 [v1.1 第 12 节 A–G](docs/archive/项目开发文档-v1.1.md) 操作。建议为每轮使用新的会话，并记录 session_id（浏览器 `/api/v1/session/me` 响应）和失败现象：

| 场景 | 操作与应观察结果 | 自动证据 |
|---|---|---|
| A 读题/视频 | 直接进入；播放、暂停、关闭重开；视频缺失仍能进入 | `media-and-freeze.spec.ts`、导出视频事件核查 |
| B 制作 | 上传教材文字，发送，复制代码并粘贴，手动运行 | `workflow.spec.ts` 第一例 |
| C 调试 | 触发点击异常与 Promise 异常，复制错误，再运行 | 浏览器控制台桥接与 pytest preview 用例 |
| D 计划/保活 | 修改计划、收起，操作游戏，任务往返后游戏计数不变 | 浏览器 iframe 计数断言 |
| E 提交 | 取消；确认 A 后继续改 B；再次提交 | 延迟真实提交请求的冻结用例 |
| F 恢复 | 拦截本地 API，编辑/运行；恢复连接，检查补传 | outbox 单元、浏览器中断、写盘失败与重启集成 |
| G 隔离/归档 | 3 个独立上下文写不同标记，导出、恢复 | 三上下文浏览器测试、`audit_e2e.py` |

**仍需真实人工评测**：Windows Alt-Tab/最小化/视频全屏、中文输入法组合输入、键盘焦点与触摸模拟、连续使用 30 分钟。自动测试通过不能替代这些人工结论。复测时只有“实现 + 自动测试 + 人工/数据核查 + 证据记录”全部满足的清单项才勾选。

## 6. 导出、备份与恢复

结束会话、同步队列归零后导出（导出路径必须是尚不存在的新文件）：

```powershell
.venv/Scripts/python.exe scripts/export_session.py --env-file .env.local --session-id <session_id> --output artifacts/session-01.zip
.venv/Scripts/python.exe scripts/validate_export.py --input artifacts/session-01.zip
```

导出不包含 JWT 密钥、DeepSeek 密钥和座位入口。备份包含座位入口和全库，供本机恢复使用。**先停止后端，再备份**；运行锁会拒绝对仍在使用的数据目录进行维护。

```powershell
.venv/Scripts/python.exe scripts/backup_local.py --env-file .env.local --output artifacts/local-backup.zip
.venv/Scripts/python.exe scripts/restore_local.py --input artifacts/local-backup.zip --target data/restored-01
```

恢复命令拒绝覆盖现有目录，检查文件哈希、数据库完整性和引用。要启动恢复库，复制 `.env.local` 为 `.env.restored.local`，将 `DATA_DIR` 和 `DATABASE_URL` 都改为恢复目录；用相应 `--env-file` 启动。JWT 密钥不在备份中，保留本机配置或重新生成后从 seat 入口认证。

## 7. AI 配置与后续边界

`.env.local` 中 `FAKE_AI_SCENARIO` 支持 `success/slow_stream/first_token_timeout/partial_then_error/rate_limited`。修改后重启后端；只在合成测试会话中切换场景。

真实联调时显式设置 `AI_PROVIDER=deepseek`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`。密钥只留后端，不写入日志、浏览器或导出。DeepSeek SSE 协议已通过模拟 HTTP 测试，**实际外部服务调用未验证**；不会在真实服务失败时偷偷退回 fake。

当前是单 worker 本地版本。真实教室并发、局域网、安全发布包、教师后台、希沃设备与长期运维均保留到部署阶段。iframe 无法保证隔离死循环占满浏览器线程，关闭卡死标签页后只能恢复已持久化草稿。
