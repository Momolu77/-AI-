"""
状态识别服务

基于交互日志提取特征并计算PME三维状态
"""

import math
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional


def extract_features(events: List[dict]) -> dict:
    """
    从事件日志中提取12个核心特征

    返回: {特征名: 特征值 或 None, 特征名_status: 状态标识}
    """
    features = {}

    if not events:
        return _empty_features()

    # 按时间排序
    events = sorted(events, key=lambda e: e['server_timestamp'])

    # 会话开始时间
    session_start = datetime.fromisoformat(events[0]['server_timestamp'])

    # 按类型分类事件
    prompts = [e for e in events if e['event_type'] == 'prompt']
    ai_replies = [e for e in events if e['event_type'] == 'ai_reply']
    edits = [e for e in events if e['event_type'] == 'edit']
    verifies = [e for e in events if e['event_type'] == 'verify']
    switches = [e for e in events if e['event_type'] == 'focus_switch']
    page_views = [e for e in events if e['event_type'] == 'page_view']

    # ========== Planning 特征 ==========

    # P1: 首次Prompt延迟
    if prompts:
        first_prompt_time = datetime.fromisoformat(prompts[0]['server_timestamp'])
        features['p1_delay'] = (first_prompt_time - session_start).total_seconds()
        features['p1_status'] = 'observed'
    else:
        features['p1_delay'] = None
        features['p1_status'] = 'unknown'

    # P2: Prompt目标明确度 (需要LLM判断，这里用简单启发式模拟)
    if prompts:
        features['p2_goal_clarity'] = _judge_goal_clarity(prompts[0]['content'])
        features['p2_status'] = 'observed'
    else:
        features['p2_goal_clarity'] = None
        features['p2_status'] = 'unknown'

    # P3: Prompt任务拆解程度
    if prompts:
        features['p3_decomposition'] = _count_task_steps(prompts[0]['content'])
        features['p3_status'] = 'observed'
    else:
        features['p3_decomposition'] = None
        features['p3_status'] = 'unknown'

    # P4: 任务阅读时长
    task_views = [e for e in page_views if '任务' in e.get('content', '')]
    if task_views and task_views[0].get('metadata', {}).get('duration'):
        features['p4_reading'] = task_views[0]['metadata']['duration']
        features['p4_status'] = 'observed'
    else:
        features['p4_reading'] = 0
        features['p4_status'] = 'not_applicable'

    # ========== Monitoring 特征 ==========

    # M1: AI回复阅读时长
    if ai_replies:
        reading_times = []
        for i, reply in enumerate(ai_replies):
            reply_time = datetime.fromisoformat(reply['server_timestamp'])
            # 找到下一个事件
            next_events = [e for e in events if datetime.fromisoformat(e['server_timestamp']) > reply_time]
            if next_events:
                next_time = datetime.fromisoformat(next_events[0]['server_timestamp'])
                delta = (next_time - reply_time).total_seconds()
                if 0 < delta < 300:  # 排除异常值（>5分钟视为离席）
                    reading_times.append(delta)

        if reading_times:
            features['m1_reading'] = sum(reading_times) / len(reading_times)
            features['m1_status'] = 'observed'
        else:
            features['m1_reading'] = None
            features['m1_status'] = 'insufficient_data'
    else:
        features['m1_reading'] = None
        features['m1_status'] = 'insufficient_data'

    # M2: 区域切换频率
    if switches:
        cross_area = sum(1 for e in switches if e.get('metadata', {}).get('is_cross_area', False))
        features['m2_switch'] = cross_area / len(events) if len(events) > 5 else 0.1
        features['m2_status'] = 'observed' if len(switches) >= 2 else 'insufficient_data'
    else:
        features['m2_switch'] = 0.1  # 默认基线
        features['m2_status'] = 'insufficient_data'

    # M3: 追问/澄清比例（降低最小Prompt数要求到2）
    if len(prompts) >= 2:
        followup_count = sum(1 for p in prompts if _is_followup(p['content']))
        features['m3_followup_ratio'] = followup_count / len(prompts)
        features['m3_status'] = 'observed'
    else:
        features['m3_followup_ratio'] = None
        features['m3_status'] = 'insufficient_data'

    # M4: 指出AI错误次数（降低最小Prompt数要求到2）
    if len(prompts) >= 2:
        error_count = sum(1 for p in prompts if _is_error_pointing(p['content']))
        features['m4_error_count'] = error_count
        features['m4_status'] = 'observed'
    else:
        features['m4_error_count'] = None
        features['m4_status'] = 'insufficient_data'

    # ========== Evaluation 特征 ==========

    # E1: AI回复后编辑率（加权优化 + 滑动衰减窗口）
    if ai_replies and edits:
        edit_after_ai = 0
        total_weight = 0

        for reply in ai_replies:
            reply_time = datetime.fromisoformat(reply['server_timestamp'])

            # 找到该AI回复后的所有编辑，并根据时间计算权重
            for e in events:
                if e['event_type'] == 'edit':
                    edit_time = datetime.fromisoformat(e['server_timestamp'])
                    delay = (edit_time - reply_time).total_seconds()

                    if 0 < delay <= 120:  # 扩展到120秒窗口
                        # 滑动衰减：0-30s权重1.0, 30-60s权重0.8, 60-120s权重0.5
                        if delay <= 30:
                            weight = 1.0
                        elif delay <= 60:
                            weight = 0.8
                        else:
                            weight = 0.5

                        # 结合编辑深度（调整基础权重，避免浅层编辑得分过低）
                        depth = _judge_edit_depth(e['content'])
                        weighted_score = weight * (0.5 + 0.5 * depth)

                        edit_after_ai += weighted_score
                        total_weight += 1.0
                        break  # 每个AI回复只计算第一次编辑

        features['e1_edit_rate'] = edit_after_ai / len(ai_replies) if ai_replies else 0
        features['e1_status'] = 'observed'
    else:
        features['e1_edit_rate'] = None
        features['e1_status'] = 'insufficient_data'

    # E2: 编辑深度
    if edits:
        depths = [_judge_edit_depth(e['content']) for e in edits]
        features['e2_depth'] = sum(depths) / len(depths)
        features['e2_status'] = 'observed'
    else:
        features['e2_depth'] = None
        features['e2_status'] = 'insufficient_data'

    # E3: 自主编辑比例
    if len(edits) >= 2:
        self_edits = sum(1 for e in edits if not e.get('metadata', {}).get('triggered_by_ai', False))
        features['e3_self_ratio'] = self_edits / len(edits)
        features['e3_status'] = 'observed'
    else:
        features['e3_self_ratio'] = None
        features['e3_status'] = 'insufficient_data'

    # E4: 验证频率
    if len(events) > 5:
        features['e4_verify'] = len(verifies) / len(events)
        features['e4_status'] = 'observed' if verifies else 'not_applicable'
    else:
        features['e4_verify'] = 0
        features['e4_status'] = 'insufficient_data'

    return features


def _empty_features() -> dict:
    """返回空特征集"""
    features = {}
    for prefix in ['p1', 'p2', 'p3', 'p4', 'm1', 'm2', 'm3', 'm4', 'e1', 'e2', 'e3', 'e4']:
        features[f'{prefix}_delay' if prefix == 'p1' else
                f'{prefix}_goal_clarity' if prefix == 'p2' else
                f'{prefix}_decomposition' if prefix == 'p3' else
                f'{prefix}_reading' if prefix in ['p4', 'm1'] else
                f'{prefix}_switch' if prefix == 'm2' else
                f'{prefix}_followup_ratio' if prefix == 'm3' else
                f'{prefix}_error_count' if prefix == 'm4' else
                f'{prefix}_edit_rate' if prefix == 'e1' else
                f'{prefix}_depth' if prefix == 'e2' else
                f'{prefix}_self_ratio' if prefix == 'e3' else
                f'{prefix}_verify'] = None
        features[f'{prefix.split("_")[0]}_status'] = 'unknown'
    return features


# ========== 启发式判断函数（简化版，实际应调用LLM） ==========

def _judge_goal_clarity(prompt: str) -> float:
    """判断Prompt目标明确度"""
    # 明确目标的特征
    clear_patterns = [
        r'写.*\d+字',
        r'包括.*和.*',
        r'要求：',
        r'具体.*：',
        r'第.*步',
        r'论证',
        r'分析',
        r'说明.*意义'
    ]

    matches = sum(1 for p in clear_patterns if re.search(p, prompt))

    # 模糊目标的特征
    if len(prompt) < 15 or any(w in prompt for w in ['帮我写', '给我点', '写个', '来一段']):
        return 0.0

    return 1.0 if matches >= 2 else 0.5 if matches >= 1 else 0.0


def _count_task_steps(prompt: str) -> int:
    """统计任务拆解步骤数"""
    patterns = [
        r'先.*再.*然后',
        r'首先.*其次.*最后',
        r'第[一二三四五1-5]步',
        r'\d+[\.、]',
        r'[一二三四五][\.、]'
    ]

    count = 0
    for pattern in patterns:
        matches = re.findall(pattern, prompt)
        count += len(matches)

    # 检测明确的步骤编号
    numbered_steps = len(re.findall(r'[1-5][\.\)、]', prompt))
    count = max(count, numbered_steps)

    return min(count, 5)  # 最多5步


def _is_followup(prompt: str) -> bool:
    """判断是否为追问/澄清"""
    keywords = [
        '是什么意思', '为什么', '能否详细', '能不能解释',
        '举个例子', '具体来说', '不太明白', '不清楚',
        '能再', '可以再', '进一步', '更详细'
    ]
    return any(kw in prompt for kw in keywords)


def _is_error_pointing(prompt: str) -> bool:
    """判断是否指出AI错误"""
    keywords = [
        '不对', '有误', '错误', '不准确', '不正确',
        '应该是', '实际上', '其实', '有问题',
        '太笼统', '太宽泛', '不够具体'
    ]
    return any(kw in prompt for kw in keywords)


def _judge_edit_depth(edit_desc: str) -> float:
    """判断编辑深度"""
    # 深层编辑特征
    deep_keywords = ['重新组织', '调整论证', '改变结构', '大幅重写', '重构']
    # 中等编辑特征
    medium_keywords = ['调整表述', '增删句子', '补充内容', '整合', '改写']
    # 浅层编辑特征
    shallow_keywords = ['错别字', '标点', '复制粘贴', '改了', '格式']

    if any(kw in edit_desc for kw in deep_keywords):
        return 1.0
    elif any(kw in edit_desc for kw in medium_keywords):
        return 0.5
    elif any(kw in edit_desc for kw in shallow_keywords):
        return 0.0
    else:
        return 0.5  # 默认中等


# ========== 状态计算 ==========

def normalize_linear(value: Optional[float], min_val: float, max_val: float, reverse: bool = False) -> Optional[float]:
    """线性标准化到[0,1]"""
    if value is None:
        return None
    value = max(min_val, min(max_val, value))  # clamp
    score = (value - min_val) / (max_val - min_val) if max_val > min_val else 0
    return 1 - score if reverse else score


def normalize_gaussian(value: Optional[float], optimal: float, sigma: float) -> Optional[float]:
    """高斯标准化，optimal处得1分"""
    if value is None:
        return None
    return math.exp(-((value - optimal) ** 2) / (2 * sigma ** 2))


def compute_metacog_state(features: dict) -> dict:
    """
    基于特征计算PME三维状态

    返回: {
        'planning': float or None,
        'monitoring': float or None,
        'evaluation': float or None,
        'confidence': {...},
        'status': {...},
        'feature_coverage': float,
        'features': dict
    }
    """

    # Planning
    p1 = normalize_gaussian(features.get('p1_delay'), optimal=60, sigma=50)
    p2 = features.get('p2_goal_clarity')  # 已经是0/0.5/1
    p3 = normalize_linear(features.get('p3_decomposition'), 0, 5)
    p4 = normalize_gaussian(features.get('p4_reading'), optimal=120, sigma=100)

    p_scores = [s for s in [p1, p2, p3, p4] if s is not None]
    planning_score = sum(p_scores) / len(p_scores) if p_scores else None
    planning_confidence = len(p_scores) / 4
    planning_status = 'observed' if len(p_scores) >= 2 else 'insufficient_data'

    # Monitoring (优化高斯参数以更好区分高低元认知)
    m1 = normalize_gaussian(features.get('m1_reading'), optimal=15, sigma=10)  # 降低sigma使3秒得分更低
    m2 = normalize_gaussian(features.get('m2_switch'), optimal=0.20, sigma=0.12)  # 提高optimal，降低sigma
    m3 = normalize_gaussian(features.get('m3_followup_ratio'), optimal=0.2, sigma=0.15)
    m4 = normalize_gaussian(features.get('m4_error_count'), optimal=2, sigma=2)

    m_scores = [s for s in [m1, m2, m3, m4] if s is not None]
    monitoring_score = sum(m_scores) / len(m_scores) if m_scores else None
    monitoring_confidence = len(m_scores) / 4
    monitoring_status = 'observed' if len(m_scores) >= 2 else 'insufficient_data'

    # Evaluation
    e1 = normalize_linear(features.get('e1_edit_rate'), 0, 1)
    e2 = features.get('e2_depth')  # 已经是0-1
    e3 = normalize_linear(features.get('e3_self_ratio'), 0, 1)
    e4 = normalize_linear(features.get('e4_verify'), 0, 0.2)

    e_scores = [s for s in [e1, e2, e3, e4] if s is not None]
    evaluation_score = sum(e_scores) / len(e_scores) if e_scores else None
    evaluation_confidence = len(e_scores) / 4
    evaluation_status = 'observed' if len(e_scores) >= 2 else 'insufficient_data'

    # 特征覆盖率（修正bug：使用正确的特征键名）
    all_feature_keys = [
        'p1_delay', 'p2_goal_clarity', 'p3_decomposition', 'p4_reading',
        'm1_reading', 'm2_switch', 'm3_followup_ratio', 'm4_error_count',
        'e1_edit_rate', 'e2_depth', 'e3_self_ratio', 'e4_verify'
    ]
    feature_coverage = sum(1 for key in all_feature_keys if features.get(key) is not None) / 12

    return {
        'planning': round(planning_score, 3) if planning_score is not None else None,
        'monitoring': round(monitoring_score, 3) if monitoring_score is not None else None,
        'evaluation': round(evaluation_score, 3) if evaluation_score is not None else None,
        'confidence': {
            'planning': round(planning_confidence, 2),
            'monitoring': round(monitoring_confidence, 2),
            'evaluation': round(evaluation_confidence, 2)
        },
        'status': {
            'planning': planning_status,
            'monitoring': monitoring_status,
            'evaluation': evaluation_status
        },
        'feature_coverage': round(feature_coverage, 2),
        'computation_version': 'v0.1.0',
        'features': features
    }
