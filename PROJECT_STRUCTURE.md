# 项目文件结构

```
9.13毕业系统/
│
├── backend/                          # 后端服务
│   ├── app/
│   │   ├── api/
│   │   │   └── websocket.py         # WebSocket接口
│   │   ├── models/
│   │   │   └── event.py             # 数据模型
│   │   ├── services/
│   │   │   ├── state_recognizer.py  # ✅ 状态识别器（核心）
│   │   │   └── intervention.py      # ✅ 干预决策器（核心）
│   │   └── main.py                  # FastAPI主应用
│   │
│   ├── tests/                        # 测试套件
│   │   ├── generate_mock_data.py    # ✅ 模拟数据生成器
│   │   ├── test_state_recognition.py # ✅ 状态识别测试
│   │   ├── mock_data/               # 生成的测试数据（运行后创建）
│   │   │   ├── high_metacog.json
│   │   │   ├── low_metacog.json
│   │   │   ├── mixed_metacog.json
│   │   │   └── planning_weak.json
│   │   ├── README.md                # ✅ 测试使用指南
│   │   ├── TEST_FINAL_SUMMARY.md    # ✅ 测试结果总结
│   │   └── DELIVERY_CHECKLIST.md    # ✅ 交付清单
│   │
│   ├── requirements.txt             # Python依赖
│   └── .env                         # 环境变量
│
├── frontend/                        # 前端应用（待开发）
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx   # 对话界面
│   │   │   ├── StateVisualizer.tsx # 状态可视化
│   │   │   └── InterventionPanel.tsx # 干预提示面板
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts     # WebSocket连接钩子
│   │   └── App.tsx
│   ├── package.json
│   └── tsconfig.json
│
├── docs/                            # 文档
│   ├── 产品设计文档.md               # ✅ 完整产品需求（v0.2）
│   ├── 核心指标筛选方案.md           # ✅ 12个指标定义（v0.2）
│   └── API文档.md                   # API接口规范
│
└── PROJECT_STRUCTURE.md             # 本文件

```

## 核心文件说明

### 后端核心（已完成）

| 文件 | 说明 | 状态 |
|------|------|------|
| `state_recognizer.py` | 12个特征提取 + PME状态计算 | ✅ v0.1.2 |
| `intervention.py` | 干预决策状态机 + 4种策略 | ✅ v0.1.0 |
| `generate_mock_data.py` | 4种场景模拟数据生成 | ✅ v0.1.0 |
| `test_state_recognition.py` | 端到端测试验证 | ✅ v0.1.0 |

### 文档（已完成）

| 文件 | 说明 | 状态 |
|------|------|------|
| `产品设计文档.md` | 产品需求、架构设计 | ✅ v0.2 |
| `核心指标筛选方案.md` | 12个指标的理论依据 | ✅ v0.2 |
| `TEST_FINAL_SUMMARY.md` | 测试结果与问题分析 | ✅ v0.1.2 |
| `README.md` (tests) | 测试使用指南 | ✅ v0.1.1 |
| `DELIVERY_CHECKLIST.md` | 交付验收清单 | ✅ v0.1.2 |

### 前端（待开发）

| 组件 | 说明 | 优先级 |
|------|------|--------|
| `ChatInterface.tsx` | 对话界面 + 实时数据采集 | 🔴 高 |
| `StateVisualizer.tsx` | PME状态3D雷达图 | 🟡 中 |
| `InterventionPanel.tsx` | 干预提示弹窗 | 🔴 高 |
| `useWebSocket.ts` | WebSocket连接管理 | 🔴 高 |

## 数据流

```
用户操作（前端）
    ↓ WebSocket
FastAPI 采集层 (websocket.py)
    ↓ 存储
PostgreSQL (events表)
    ↓ 读取
状态识别器 (state_recognizer.py)
    ↓ 12个特征 → PME分数
干预决策器 (intervention.py)
    ↓ 判断是否干预
生成式AI (Anthropic Claude API)
    ↓ 生成干预内容
WebSocket 推送
    ↓
前端展示 (InterventionPanel.tsx)
```

## 快速启动

### 运行测试

```bash
cd backend
python tests/generate_mock_data.py      # 生成4种场景数据
python tests/test_state_recognition.py  # 运行测试验证
```

### 启动后端（开发中）

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 启动前端（待开发）

```bash
cd frontend
npm install
npm run dev
```

## 版本历史

| 版本 | 日期 | 完成内容 |
|------|------|---------|
| v0.1.0 | 2026-09-14 上午 | 状态识别 + 干预决策 + 模拟数据 |
| v0.1.1 | 2026-09-14 中午 | 修正4个bug（E1/M3/M4/覆盖率） |
| v0.1.2 | 2026-09-14 下午 | 优化M1参数（低元认知M从0.70→0.61） |

## 下一个里程碑：v0.2.0

**目标：** 前端基础功能 + 真实用户测试准备

**任务清单：**
- [ ] ChatInterface.tsx（对话界面）
- [ ] StateVisualizer.tsx（状态可视化）
- [ ] useWebSocket.ts（WebSocket连接）
- [ ] E1加权公式优化
- [ ] M2参数微调
- [ ] 用户授权文档

**预计完成：** 本周内

---

**文档生成时间：** 2026-09-14  
**项目状态：** 后端核心完成，前端待开发
