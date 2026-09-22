# 本地功能基线验收记录

日期：2026-09-22。实现编号：`local-v0.1.0-20260922`。开发依据为归档 v1.1；本记录与 [实施清单](../development-checklist-v1.1.md) 配套，不修改原归档中的历史清单。

**结论：主要功能实现和自动验收通过，可以开始本机试用；整体验收保留 4 项 P0 未勾选。** 尚未以此结论宣称真实 DeepSeek、课堂部署、真实触控设备或所有人工评测通过。

## 环境与交付

- Windows 11 build 26200，Intel Core i5-1155G7，Python 3.13.11、Node 24.13.0、npm 11.6.2。
- 浏览器：Microsoft Edge 153.0.4234.48；E2E 用其 headless 模式和真实浏览器引擎。
- 前端 Vue 3 / TypeScript / Vuetify / Pinia / CodeMirror 6；后端 FastAPI / SQLite；精确依赖记录在 `frontend/package-lock.json` 与 `backend/requirements.lock.txt`。
- AI：`fake-local-v1`。DeepSeek adapter 的 HTTP 协议使用模拟响应验证，未发送任何真实外部 AI 请求。
- 手工入口监听 `127.0.0.1:5173/8000`；自动 E2E 独占 `127.0.0.1:5174/8001`，每轮独立数据目录且关闭 HMR/热重载。
- 启动、停止、重启脚本与 CLI 备份/恢复已实测；没有覆盖现有目录。PowerShell 脚本以 UTF-8 BOM 保存，兼容本机 Windows PowerShell 5 的中文读取。

## 自动测试结果

| 检查 | 实际结果 | 证据 |
|---|---|---|
| Ruff | 通过，退出码 0 | `python -m ruff check backend scripts` |
| pytest 单元 + 接口集成 | **50 passed**，无跳过 | [backend-results.xml](../../artifacts/backend-results.xml) |
| 前端 ESLint | 通过，退出码 0；1 条审计提醒 | `ChatPanel.vue` 的 `v-html` 只接收 DOMPurify 清洗后的 Markdown |
| TypeScript | 通过，退出码 0 | `npm --prefix frontend run typecheck`；build 同样执行 vue-tsc |
| Vitest | **11 passed**，无跳过 | [frontend-results.xml](../../artifacts/frontend-results.xml) |
| Vite build | 通过，退出码 0 | `frontend/dist/`；存在包体积及依赖注释提示，非构建失败 |
| Playwright | **5 passed**，无跳过 | [HTML 报告](../../artifacts/playwright-report/index.html)、[JUnit](../../artifacts/e2e-results.xml) |
| 数据核查与恢复 | 通过 | [data-quality-report.json](../../artifacts/data-quality-report.json) |
| npm 依赖审计 | 安装时 0 个已报告漏洞 | 锁定 Vitest 4.1.11 系列，保留 npm lockfile |

后端测试覆盖 30 类事件的合法、缺字段、额外字段和错误类型；JWT/超时、幂等和冲突、跨会话对象、版本冲突、预览签名及消息、真实附件解析、SSE、失败片段、显式重试、全局并发 2 与 3 会话排队、不可变提交、写盘失败、pending 重启、数据库锁、备份及恢复。

前端测试覆盖 Unicode/emoji/清空/撤销差分、编辑合并、outbox 中断/部分成功/拒绝/应急恢复、收尾等待在途批次、发送状态和预览消息来源验证。框架 TestClient 有弃用提示，当前锁定版本下测试通过，后续依赖升级时处理。

## 浏览器操作与数据核对

5 个 E2E 场景直接使用本机 API 与 SQLite，只有 AI provider 是 fake：

1. 视频初始暂停、真实播放超过 1 秒、暂停关闭重开保留位置；拦截视频为 404 后仍能进入工作区。
2. 提交 A 的 HTTP 请求被测试装置暂缓；编辑器改为 B 并先保存；释放请求后第一份归档仍为 A，第二次提交为 B。
3. 附件上传、仅 READY 可发送、AI 回复、浏览器剪贴板复制代码/粘贴、手动运行、游戏点击、计划、任务往返、同内容重新运行归零、原始错误复制、取消/多次提交、刷新恢复和结束。
4. 拦截真实本地 API 后编辑并运行失败，旧预览保留；解除拦截后草稿落库、事件补传，刷新后可恢复。
5. 三个独立 BrowserContext 写入不同标记，状态不串线；相同会话重复标签页显示只读入口错误；分别结束收尾。

核查脚本实际检查了 **7 个会话、105 条事件、27 类浏览器实际事件、13 条合并编辑事件重放**。55 个由浏览器发出的独立合法事件 ID 全部找到，缺失 0；传输重试没有重复事件。其余 3 类 `attachment_failed/ai_response_failed/submit_failed` 由接口故障注入测试验证，不伪称成功流浏览器用例已触发这些失败。

所有 7 个会话均结束，`task_started` 首次落库，入库序号连续，身份未串线；预览、回复、附件、提交和错误引用均可解析。成功提交 HTML/计划与确认时正文一致；保存/自动检查点没有被当作编辑行为事件。差分采用 UTF-16 坐标，核对到对应不可变代码/计划版本。

每个会话分别导出 JSONL/CSV/HTML ZIP，再校验文件哈希与引用；全库通过 SQLite backup 备份，恢复到独立 `artifacts/e2e-*-restored/`，数据库完整性、外键和引用文件检查通过。具体 session_id、恢复目录、事件 ID 在质量报告中；对应本轮目录记录于 [e2e-current.json](../../artifacts/e2e-current.json)，该测试索引含模拟座位入口，仅供本机开发。

界面截图：[任务页](../../artifacts/task-page.png)、[工作区](../../artifacts/workbench.png)。这些截图辅助检查布局，不作为数据库正确性的替代证据。

## 本机性能记录

使用单 worker uvicorn、真实回环 HTTP、100,040 字节 HTML、50 条事件批次，各采样 30 次。使用热连接，不包括依赖安装、真实 AI 或 UI 首次加载。原始样本见 [performance.json](../../artifacts/performance.json)。

| 操作 | P95 | v1.1 本机目标 |
|---|---:|---:|
| 保存代码 | 30.143 ms | ≤ 1,000 ms |
| 创建预览 | 30.201 ms | ≤ 1,000 ms |
| 50 条事件批次 | 483.532 ms | ≤ 500 ms |

三会话同时请求测试确认全局最多 2 个 provider 在运行，其余排队；UI 的消息区不锁住其他编辑区。这些数据是该开发机上的本地观察，不代表 20 台课堂性能。

## 尚未验收与明确边界

- **P0-16 / MAN-02**：真实中文输入法组合输入、撤销/重做、Windows 键盘焦点操作，需要人工复验。浏览器自动剪贴板与差分测试已通过。
- **P0-26 / MAN-01**：Alt-Tab、最小化、真正视频全屏时的可见性信号，需要本机人工操作。普通 blur 不被直接当作离开。
- **P0-28**：主动结束、刷新、API 中断、服务 pending 恢复已测；操作系统强制杀掉浏览器后重新打开的完整人工链路仍待复验。
- **P0-30**：A–G 主流程有自动证据，以上人工项、30 分钟持续使用和 UI 冷/热启动各 30 次测量未执行，因此不勾选整体完成。
- 真实 DeepSeek、扫描 PDF OCR、图片视觉输入、杀毒引擎、教师后台、局域网、20 台设备和希沃测试均未宣称完成。
- 当前包体积约 950 KB JavaScript（gzip 约 328 KB）。本地使用可运行，分包/懒加载与长时间资源观察保留到体验优化。
- iframe 沙箱保护父页面访问和消息通道，但不承诺隔离死循环导致的浏览器卡死；只能恢复最后已持久化草稿。

## 人工复验记录模板

复验时复制以下内容，并将文件路径填写到对应清单项后再勾选：

```text
清单 ID / MAN 编号：
实现编号：local-v0.1.0-20260922
Windows / 浏览器 / 输入法：
任务版本 / session_id / 数据目录：
具体操作（含切窗方式、输入法组合/撤销、关闭方式或连续时长）：
界面实际结果：
outbox 排空、事件 ID、导出校验结果：
截图/视频/日志路径：
发现的问题与修复后复测结果：
结论（通过 / 未通过）：
执行人 / 日期：
```

本轮自动执行与数据核查：Codex。人工验收人：待填写。报告未替代人工签字。
