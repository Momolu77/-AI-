# 英语教学资源工作台 · 本地采集版 v1.3

按照 [项目开发文档 v1.3](项目开发文档.md) 和 [数据采集设计 v0.7](9.21%20数据采集设计文档.md) 改造。平台记录人机对话、操作、版本、作品及外部录屏的关联资料，不自动编码元认知行为或生成能力分数。

流程：座位入口认证 → 任务列表 → 五题背景问卷 → 任务／示例／教材／工作台 → AI 协作、编辑与手动预览 → 提交或结束归档。问卷不计正式任务时长，计划始终可选。

实现及验证范围见 [本轮验收记录](docs/acceptance/collection-v1.3-2026-10-09.md)。历史文档在 `docs/archive`，历史验收不代表新版本验收。默认使用 **fake-local-v1** 和合成教材，仅供本地工程测试。

## 本机启动

开发环境：Windows、Python 3.13.11、Node 24.13.0、Microsoft Edge。首次安装依赖需要网络，fake 模式不需要 AI 密钥。在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
npm --prefix frontend ci
.venv/Scripts/python.exe scripts/local_init.py --env-file .env.local
.venv/Scripts/python.exe scripts/seed_local.py --env-file .env.local
```

打开 seed 输出的座位入口。统一使用 `127.0.0.1`，不要混用 `localhost`。初始化执行编号迁移并保留已有记录；旧会话按原事件版本读取，不补造发生端时间，也不猜测合并历史参与者。

分别在两个终端启动：

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --env-file .env.local --host 127.0.0.1 --port 8000 --reload
```

```powershell
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

也可运行 `scripts/start_local.ps1`，通过 `scripts/stop_local.ps1` 停止其后台服务。日常数据位于配置指定的目录，默认 `data/local`；自动测试使用独立目录。

## Unit 6 教材准备状态

正式任务单元为 **Unit 6: Fantastic friends**。已整理27页原版材料包（正文、相关附录及目录介绍），页码映射见 `config/resources/unit6-fantastic-friends-source-v1.mapping.json`，任务草稿见 `config/task-templates/unit6.json`。已接入 v2 OCR PDF 与逐页校对文字（`config/resources/unit6-fantastic-friends-source-v2.reviewed.json`），阅读器显示 PDF，AI 引用使用校对正文；原始 OCR 与实际引用文字均归档。正式任务草稿不在 `config/tasks` 中。默认合成测试任务不受影响。核验记录见 [v2 接入记录](docs/acceptance/unit6-v2-integration-2026-10-13.md)；[逐页文字复核稿](docs/acceptance/unit6-page-text-review-2026-10-13.md)供研究者独立复核。

本地试用真实教材：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_unit6_preview.py
```

若后台已运行旧代码，保存当前工作后用 `scripts/stop_local.ps1`、`scripts/start_local.ps1` 重启。使用座位入口回到任务列表，选择“Unit 6: Fantastic friends（工程试用）”。正在进行原任务时需先提交或结束；原数据保留。此脚本不改变默认任务或 AI 提供商，也不发布正式采集任务。


## 任务、身份与资料配置

- 在 `config/tasks/*.json` 发布任务，参照 `config/tasks/task-test.json`：包含任务版本、五题背景问题、示例及资源版本。服务启动或 seed 时读取配置，已建立的会话保留自己的任务快照。
- 教材放在 `config/resources`，视频和网页示例放在 `config/examples`。修改已发布资源内容必须递增 `version`，不能用相同版本覆盖。教材发布大小由 `RESOURCE_MAX_BYTES` 控制，默认100 MiB；学生附件仍为10 MiB。PDF 可配置 `reviewed_text_file`，必须匹配 PDF 指纹、页数、材料包页序、印刷页和原整册页码。版本化校对文件与原 OCR 均纳入导出和备份。
- 资料库引用和上传附件分别记录。文本、HTML、PDF、DOCX 的可提取文字可输入模型；图片、扫描件或解析失败资料不会被假装为已读取。原文件可查看。
- `seed_local` 为测试座位建立稳定匿名身份。更换学生使用同一座位时，需要明确重新分配。

分配参与者与任务（先结束该座位或参与者当前活动会话）：

```powershell
.venv/Scripts/python.exe scripts/assign_participant.py --env-file .env.local --seat 01 --participant-id P001 --task-id task-test --condition-id default
```

脚本更新任务分配和座位令牌，输出新入口。同一参与者后续任务沿用相同 `participant_id`，新任务建立新的 `session_id`。

## 采集功能与约定

- 任务选择后进入 PREPARING；完成问卷并实际显示任务要求才记录开始。刷新恢复、单写入者、页面离开候选、bfcache 与失联收尾分别处理，推定结束与主动结束分开保存。
- 四页与任务列表往返保留工作区。AI 请求、上传、草稿及预览保持原实例；调整列宽和全屏预览不自动运行。备课记录可在四页展开。
- AI 请求冻结点击时的正文、草稿版本、附件、引用与代码基线。流式回复保存历史片段、版本和显示范围；复制记录来源，不能验证的外部粘贴不猜作 AI 来源。
- 结构化提议可查看、接受或拒绝。接受后仍需点击应用；版本冲突不覆盖，应用结果保存且不自动运行。
- CodeMirror 保存 UTF-16 修改明细及汇总，区分人工编辑、粘贴和提议应用。检查点与行为事件分开，中文和 emoji 可重放。
- 手动运行先保存，成功才替换预览。记录原始日志、异常及有效激活／选择／文本提交／表单提交，过滤程序触发动作。保存失败与运行后错误分开。
- 提交在确认时冻结代码与计划，允许继续编辑、多次提交及未运行作品。最终作品取最后成功提交；无提交会话保存自动保存兜底并标明来源。
- IndexedDB outbox 与应急日志保留待传记录；未知结果沿用原编号核对。导出保存完整正文、业务记录、版本文件、时钟及质量诊断，支持向独立目录恢复备份。

共享契约 `config/events-v1.3.json` 定义 **49 个名称：48 类会话事件、1 类独立同步标记**。后端校验与前端生成类型共用此文件。`actor` 描述行为归属，`producer_id` 描述记录产生端。

`sequence_no` 始终表示服务器入库顺序。原始客户端序号、时钟、校准和因果引用单独保留；当前原始导出不自动生成研究排序，`order_version=null`，不能把导出行序当成动作先后。

## 外部录屏与课后资料

录屏由外部软件采集。研究者工具显示同步标记、导入媒体清单、实际 PTS 锚点及会话范围；学生端没有评分或标注写入接口。

```powershell
.venv/Scripts/python.exe scripts/capture_marker.py --env-file .env.local --participant-id P001 --recording-id P001-recording-01
.venv/Scripts/python.exe scripts/import_capture.py artifacts/capture-bundle.json --env-file .env.local
```

标记工具输出本机页面地址。在录屏开始、结束及分段时呈现标记，课后核对真实视频位置。**标记显示时间不等于视频 PTS**。格式、ffprobe 核验及缺失处理见 [录屏采集说明](docs/capture-v1.3.md)。

## 导出、备份与恢复

结束会话并确认同步队列归零后导出，输出文件必须尚不存在：

```powershell
.venv/Scripts/python.exe scripts/export_session.py --env-file .env.local --session-id <session_id> --output artifacts/session-01.zip
.venv/Scripts/python.exe scripts/validate_export.py --input artifacts/session-01.zip
```

ZIP 包含 JSONL/CSV、任务、对话、草稿、资源、提议、编辑、提交和采集关联。`quality.json` 记录缺失媒体／文件、未定案尝试和兜底作品；没有真实录屏时不宣称多模态归档完整。

先停止后端再备份：

```powershell
.venv/Scripts/python.exe scripts/backup_local.py --env-file .env.local --output artifacts/local-backup.zip
.venv/Scripts/python.exe scripts/restore_local.py --input artifacts/local-backup.zip --target data/restored-01
```

恢复拒绝覆盖已有目录。启动恢复库时，在单独环境文件中把 `DATA_DIR` 和 `DATABASE_URL` 指向恢复目录。会话导出不含密钥和座位入口；全库备份含座位入口，JWT 与外部 AI 密钥由本机环境配置保管。

## 验证命令

```powershell
.venv/Scripts/python.exe -m ruff check backend scripts
.venv/Scripts/python.exe scripts/generate_event_contract.py --check
.venv/Scripts/python.exe -m pytest backend/tests/unit backend/tests/integration -q --junitxml=artifacts/backend-results.xml
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit -- --run --reporter=default --reporter=junit --outputFile=../artifacts/frontend-results.xml
npm --prefix frontend run build
npm --prefix frontend run test:e2e
.venv/Scripts/python.exe scripts/audit_e2e.py
```

E2E 使用 Edge，独占 `5174/8001`，每轮生成新的 `artifacts/e2e-*`，不访问 `data/local`。浏览器报告在 `artifacts/playwright-report/index.html`。一轮全部通过后运行一次 audit，核对客户端事件落库、引用、编辑重放、导出和恢复。

## AI 与部署状态

默认 fake 支持 `success/slow_stream/first_token_timeout/partial_then_error/rate_limited`。真实服务需在后端显式配置 `AI_PROVIDER=deepseek`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`。协议已有模拟测试；本轮未调用真实外部模型，失败时不自动换成 fake。

本轮交付本地采集代码及自动验证。正式教材发布、真实录屏与 PTS 人工核验、中文输入法实机操作、长期使用和 20 台课堂并发仍需现场验收，详见本轮验收记录。
