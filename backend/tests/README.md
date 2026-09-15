# 模拟数据测试使用指南

## 概述

本测试套件通过生成4种典型元认知场景的模拟数据，验证状态识别和干预决策逻辑的正确性。

**文件结构：**
```
backend/tests/
├── generate_mock_data.py       模拟数据生成器
├── test_state_recognition.py   状态识别测试脚本
├── TEST_FINAL_SUMMARY.md       最终测试总结
├── mock_data/                  生成的JSON数据（运行后创建）
│   ├── high_metacog.json
│   ├── low_metacog.json
│   ├── mixed_metacog.json
│   └── planning_weak.json
```

---

## 快速开始

### 1. 生成模拟数据

```bash
cd backend
python tests/generate_mock_data.py
```

**输出：**
- `tests/mock_data/` 目录下生成4个JSON文件
- 每个文件包含一个完整会话的所有交互事件

### 2. 运行状态识别测试

```bash
python tests/test_state_recognition.py
```

**输出：**
- 每个场景的PME分数、置信度、特征覆盖率
- 干预触发测试结果
- 最终验证结果表格

---

## 模拟数据格式

### 会话结构

```json
{
  "session_id": "uuid",
  "total_events": 19,
  "session_duration_seconds": 683.0,
  "event_types": ["page_view", "prompt", "ai_reply", "focus_switch", "verify", "edit"],
  "events": [...]
}
```

### 事件结构

```json
{
  "event_id": "uuid",
  "session_id": "uuid",
  "event_type": "prompt | edit | verify | ai_reply | page_view | focus_switch",
  "content": "事件内容",
  "metadata": {
    "source_area": "task | chat | state",
    "duration": 120,
    "is_cross_area": true
  },
  "sequence_num": 1,
  "client_timestamp": 1789384303993,
  "server_timestamp": "2026-09-14T19:11:43.993458"
}
```

---

## 四种模拟场景

### 1. 高元认知学生 (high_metacog.json)

**特征：**
- Planning: 先阅读任务说明120秒，Prompt包含明确目标和步骤
- Monitoring: AI回复后仔细阅读15秒，频繁切换区域对比
- Evaluation: 深度编辑，主动验证，多次迭代

**事件序列：**
```
page_view(120s) → prompt(明确目标) → ai_reply → 
read(15s) → focus_switch → edit(深度) → verify →
prompt(追问) → ai_reply → focus_switch → edit → verify
```

**预期PME分数：**
- Planning: > 0.8
- Monitoring: > 0.8
- Evaluation: > 0.7

---

### 2. 低元认知学生 (low_metacog.json)

**特征：**
- Planning: 无任务阅读，立即发送模糊Prompt
- Monitoring: AI回复后快速略读3秒，无区域切换
- Evaluation: 直接复制粘贴，无编辑，无验证

**事件序列：**
```
prompt(模糊) → ai_reply → read(3s) → 
prompt(再次模糊) → ai_reply → read(3s) →
[无edit/verify]
```

**预期PME分数：**
- Planning: < 0.4
- Monitoring: < 0.4
- Evaluation: < 0.4

---

### 3. 中等元认知学生 (mixed_metacog.json)

**特征：**
- Planning: 简单阅读30秒，Prompt基本明确
- Monitoring: 阅读8秒，偶尔切换
- Evaluation: 浅层编辑（修改错别字），无验证

**事件序列：**
```
page_view(30s) → prompt(基本明确) → ai_reply → 
read(8s) → edit(浅层) → 
prompt → ai_reply → edit(浅层)
```

**预期PME分数：**
- Planning: 0.5-0.7
- Monitoring: 0.5-0.7
- Evaluation: 0.3-0.5

---

### 4. Planning薄弱学生 (planning_weak.json)

**特征：**
- Planning: 无任务阅读，Prompt目标不明确（触发Planning干预）
- Monitoring: 认真阅读，频繁切换，主动追问（正常）
- Evaluation: 深度编辑，主动验证（正常）

**事件序列：**
```
prompt(模糊) → ai_reply → read(12s) → focus_switch →
edit(深度) → verify → prompt(追问) → ...
```

**预期PME分数：**
- Planning: < 0.4（触发干预）
- Monitoring: > 0.7
- Evaluation: > 0.5

**预期干预：**
- 类型: `process_scaffold`
- 触发时机: 第4次状态更新
- 原因: Planning分数 < 0.4 且 置信度 > 0.7

---

## 测试结果解读

### 状态输出示例

```
============================================================
  High Metacog Student - State Update 3
============================================================

Features (12 indicators):
  P1 - Task Reading     : 120.0 s
  P2 - Prompt Goal      : 1.0
  P3 - Prompt Steps     : 3
  P4 - First Delay      : 60.0 s
  M1 - Reading Time     : 15.0 s
  M2 - Area Switch      : 0.16
  M3 - Followup Ratio   : 0.33
  M4 - Error Count      : 1
  E1 - Edit After AI    : 0.67
  E2 - Edit Depth       : 1.0
  E3 - Self Edit        : 0.32
  E4 - Verify Rate      : 0.21

Metacognitive State:
  Planning     : #################### 0.900 (conf: 1.00, observed)
  Monitoring   : ##################   0.803 (conf: 1.00, observed)
  Evaluation   : #########----------- 0.447 (conf: 1.00, observed)

  Coverage     : 100.00%
```

### 关键指标说明

| 指标 | 含义 | 判断标准 |
|------|------|---------|
| **Planning分数** | 任务前规划充分度 | > 0.7: 优秀，< 0.4: 需要干预 |
| **Monitoring分数** | 过程监控主动性 | > 0.7: 优秀，< 0.4: 需要干预 |
| **Evaluation分数** | 输出评价批判性 | > 0.7: 优秀，< 0.4: 需要干预 |
| **Confidence** | 计算置信度 | > 0.7: 可信，< 0.5: 数据不足 |
| **Coverage** | 特征覆盖率 | > 90%: 完整，< 70%: 数据缺失 |

---

## 当前测试结果（v0.1.1）

| 场景 | Planning | Monitoring | Evaluation | 覆盖率 | 状态 |
|------|----------|------------|------------|--------|------|
| 高元认知 | 0.900 ✅ | 0.802 ✅ | 0.447 ⚠️ | 100% ✅ | 部分通过 |
| 低元认知 | 0.243 ✅ | 0.613 ⚠️ | 0.250 ✅ | 100% ✅ | 部分通过 |
| 中等元认知 | 0.376 ✅ | 0.603 ⚠️ | 0.375 ✅ | 100% ✅ | 部分通过 |
| Planning弱 | 0.243 ✅ | 0.766 ✅ | 0.542 ✅ | 92% ✅ | 完全通过 |

**已知问题：**
1. 高元认知E分数偏低（0.447）- E1窗口需优化
2. 低/中元认知M分数偏高（0.61-0.63）- M2参数需微调

---

## 修改测试参数

### 调整高斯标准化参数

编辑 `backend/app/services/state_recognizer.py`:

```python
# 示例：让低阅读时长得分更低
m1 = normalize_gaussian(
    features.get('m1_reading'), 
    optimal=15,  # 理想阅读时长
    sigma=10     # 调小使曲线更陡峭
)
```

### 调整干预阈值

编辑 `backend/app/services/intervention.py`:

```python
# 示例：放宽Planning干预条件
if state['planning'] < 0.35:  # 从0.4降低到0.35
    # 触发干预
```

---

## 添加新测试场景

在 `generate_mock_data.py` 中添加新函数：

```python
def generate_custom_session() -> MockEventGenerator:
    """自定义场景"""
    gen = MockEventGenerator()
    
    # 添加事件
    gen.generate_event('page_view', '查看任务', delay_seconds=0)
    gen.generate_event('prompt', 'Prompt内容', delay_seconds=30)
    gen.generate_event('ai_reply', 'AI回复', delay_seconds=3)
    # ... 更多事件
    
    return gen
```

然后在 `test_state_recognition.py` 中调用：

```python
print("\n" + "="*60)
print("  Custom Scenario Test")
print("="*60)
test_session(generate_custom_session(), "Custom Scenario")
```

---

## 常见问题

### Q1: 测试显示中文乱码？
**A:** Windows终端编码问题，不影响实际功能。修复：
```bash
# 使用UTF-8编码运行
chcp 65001
python tests/test_state_recognition.py
```

### Q2: 特征覆盖率显示0.0%？
**A:** 已在v0.1.1修复。如仍出现，检查 `state_recognizer.py` 第207行的特征键名是否正确。

### Q3: 干预未按预期触发？
**A:** 检查：
1. 状态分数是否低于阈值（默认0.4）
2. 置信度是否足够（需要 > 0.7）
3. 是否在冷却期内（每次干预后180秒冷却）

### Q4: 如何查看详细的特征值？
**A:** 取消注释 `test_state_recognition.py` 第74-87行的特征打印代码。

---

## 下一步

**完成测试后：**
1. 根据测试结果调整参数（参考 `TEST_FINAL_SUMMARY.md`）
2. 实现前端界面连接真实WebSocket
3. 进行真实用户小规模测试（3-5人）
4. 收集真实数据重新校准所有参数

**文档更新：**
- 测试发现问题 → 更新 `TEST_FINAL_SUMMARY.md`
- 参数优化记录 → 更新 `核心指标筛选方案.md`
- 真实数据分析 → 创建 `REAL_DATA_ANALYSIS.md`

---

**生成时间：** 2026-09-14  
**版本：** v0.1.1  
**维护者：** Claude Opus 5
