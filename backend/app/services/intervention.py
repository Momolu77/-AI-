"""
干预决策服务

基于元认知状态判断是否需要干预，并生成干预内容
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple


class InterventionStateMachine:
    """
    干预状态机

    状态流转：
    初始 → 观察期（前3个事件）→ 检查触发条件 → 冷却期（180秒）→ 可再次触发
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.event_count = 0
        self.intervention_history: List[Tuple[str, datetime]] = []  # [(type, timestamp), ...]

    def on_event(self, state: dict) -> Optional[dict]:
        """
        每次状态更新时调用

        Args:
            state: 包含planning/monitoring/evaluation分数、confidence、status、features的字典

        Returns:
            干预内容字典 或 None
        """
        self.event_count += 1

        # 观察期：前3个事件不干预
        if self.event_count <= 3:
            return None

        # 检查最大次数（每维度最多2次，共6次）
        if len(self.intervention_history) >= 6:
            return None

        # 检查冷却期（最后一次干预后180秒内不再干预）
        if self.intervention_history:
            last_intervention_time = self.intervention_history[-1][1]
            if (datetime.utcnow() - last_intervention_time).total_seconds() < 180:
                return None

        # 按优先级检查触发条件
        for check_func, dim in [
            (self._should_intervene_planning, 'planning'),
            (self._should_intervene_monitoring, 'monitoring'),
            (self._should_intervene_evaluation, 'evaluation')
        ]:
            if check_func(state):
                # 检查该维度是否已干预2次
                dim_count = sum(1 for t, _ in self.intervention_history if t == dim)
                if dim_count >= 2:
                    continue

                intervention = self._generate_intervention(dim, state)
                self.intervention_history.append((dim, datetime.utcnow()))
                return intervention

        return None

    def _should_intervene_planning(self, state: dict) -> bool:
        """判断是否需要Planning干预"""
        return (
            state.get('status', {}).get('planning') == 'observed' and
            state.get('confidence', {}).get('planning', 0) > 0.7 and
            state.get('planning') is not None and
            state.get('planning') < 0.4 and
            state.get('features', {}).get('p1_delay') is not None and
            state.get('features', {}).get('p1_delay') < 10
        )

    def _should_intervene_monitoring(self, state: dict) -> bool:
        """判断是否需要Monitoring干预"""
        return (
            state.get('status', {}).get('monitoring') == 'observed' and
            state.get('confidence', {}).get('monitoring', 0) > 0.7 and
            state.get('monitoring') is not None and
            state.get('monitoring') < 0.4 and
            state.get('features', {}).get('m1_reading') is not None and
            state.get('features', {}).get('m1_reading') < 5
        )

    def _should_intervene_evaluation(self, state: dict) -> bool:
        """判断是否需要Evaluation干预"""
        return (
            state.get('status', {}).get('evaluation') == 'observed' and
            state.get('confidence', {}).get('evaluation', 0) > 0.7 and
            state.get('evaluation') is not None and
            state.get('evaluation') < 0.4 and
            state.get('features', {}).get('e1_edit_rate') is not None and
            state.get('features', {}).get('e1_edit_rate') < 0.3
        )

    def _generate_intervention(self, dimension: str, state: dict) -> dict:
        """
        生成干预内容

        Args:
            dimension: 'planning' | 'monitoring' | 'evaluation'
            state: 当前状态

        Returns:
            干预内容字典
        """
        templates = {
            'planning': {
                'type': 'process_scaffold',
                'content': '''在继续之前，建议先思考：

1. **任务目标**：这个任务的核心目标是什么？
2. **人机分工**：你希望AI帮你完成哪部分？
3. **你的工作**：你自己需要完成哪部分？

先规划清楚再行动，可以让学习更有效率。'''
            },
            'monitoring': {
                'type': 'metacog_prompt',
                'content': '''建议仔细阅读AI的回答，思考以下问题：

1. **符合预期吗**？AI的回答是否符合你的预期？
2. **需要澄清吗**？是否有不清楚的地方需要进一步询问？
3. **准确吗**？有没有不准确或需要验证的内容？

批判性地评估AI的输出，才能更好地利用AI。'''
            },
            'evaluation': {
                'type': 'reflection_prompt',
                'content': '''AI的输出只是参考，请结合你自己的理解进行加工：

1. **需要调整什么**？哪些内容需要修改或补充？
2. **你的思考**？哪些地方可以加入你的独立思考？
3. **符合要求吗**？如何让内容更符合任务要求？

批判性加工AI内容，才能真正掌握知识。'''
            }
        }

        template = templates[dimension]

        return {
            'type': template['type'],
            'content': template['content'],
            'trigger_reason': self._format_trigger_reason(dimension, state),
            'trigger_state': {
                'planning': state.get('planning'),
                'monitoring': state.get('monitoring'),
                'evaluation': state.get('evaluation'),
                'confidence': state.get('confidence', {})
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    def _format_trigger_reason(self, dimension: str, state: dict) -> str:
        """格式化触发原因"""
        score = state.get(dimension)
        confidence = state.get('confidence', {}).get(dimension, 0)

        reasons = []
        reasons.append(f"{dimension.capitalize()} 分数较低 ({score:.2f})")

        # 添加具体原因
        if dimension == 'planning':
            if state.get('features', {}).get('p1_delay', 0) < 10:
                reasons.append("直接询问AI，未充分思考任务")
            if state.get('features', {}).get('p2_goal_clarity', 1) < 0.5:
                reasons.append("Prompt目标不明确")
        elif dimension == 'monitoring':
            if state.get('features', {}).get('m1_reading', 0) < 5:
                reasons.append("快速接受AI输出，阅读时间过短")
            if state.get('features', {}).get('m3_followup_ratio', 0) < 0.1:
                reasons.append("缺少追问和澄清")
        elif dimension == 'evaluation':
            if state.get('features', {}).get('e1_edit_rate', 0) < 0.3:
                reasons.append("直接使用AI内容，缺少加工")
            if state.get('features', {}).get('e2_depth', 0) < 0.3:
                reasons.append("编辑深度不足")

        return ' | '.join(reasons) + f" | 置信度: {confidence:.2f}"


# 干预Prompt模板（用于未来LLM生成个性化干预内容）
INTERVENTION_PROMPTS = {
    'process_scaffold': {
        'system': '你是元认知学习支持助手，帮助学生在AI协作学习中进行规划。',
        'template': '''学生正在完成写作任务，但表现出规划不足的迹象：
- 任务: {task_description}
- 问题: {trigger_reason}

请生成一个简短的规划提示（3-5句话），引导学生思考任务目标和人机分工。语气友好、启发性，不要说教。'''
    },
    'metacog_prompt': {
        'system': '你是元认知学习支持助手，帮助学生在AI协作学习中进行监控。',
        'template': '''学生正在与AI对话完成写作任务，但表现出监控不足的迹象：
- 任务: {task_description}
- 问题: {trigger_reason}

请生成一个简短的监控提示（3-5句话），引导学生批判性地评估AI输出。语气友好、启发性，不要说教。'''
    },
    'reflection_prompt': {
        'system': '你是元认知学习支持助手，帮助学生在AI协作学习中进行反思。',
        'template': '''学生正在使用AI生成的内容完成写作任务，但表现出评价不足的迹象：
- 任务: {task_description}
- 问题: {trigger_reason}

请生成一个简短的反思提示（3-5句话），引导学生批判性地加工AI内容。语气友好、启发性，不要说教。'''
    }
}


def should_trigger_intervention(state: dict, session_data: dict) -> Optional[dict]:
    """
    独立函数：判断是否需要触发干预（无状态）

    Args:
        state: 元认知状态
        session_data: 会话数据（含历史干预记录）

    Returns:
        干预内容 或 None
    """
    # 创建临时状态机
    sm = InterventionStateMachine(session_data.get('session_id', ''))
    sm.event_count = session_data.get('event_count', 0)
    sm.intervention_history = session_data.get('intervention_history', [])

    return sm.on_event(state)
