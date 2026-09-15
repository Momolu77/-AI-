"""
模拟数据生成器

生成符合协议的模拟学习会话事件，用于测试状态识别和干预逻辑。

场景类型：
1. 高元认知学生：计划充分、持续监控、批判性评价
2. 低元认知学生：直接问AI、快速接受、不加工
3. 中等元认知学生：部分维度强、部分维度弱
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import List, Dict
import random


class MockEventGenerator:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.sequence_num = 0
        self.current_time = datetime.now()
        self.events = []

    def generate_event(
        self,
        event_type: str,
        content: str,
        metadata: Dict = None,
        delay_seconds: float = 0
    ) -> Dict:
        """生成单个事件"""
        self.current_time += timedelta(seconds=delay_seconds)
        self.sequence_num += 1

        event = {
            "event_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "event_type": event_type,
            "content": content,
            "metadata": metadata or {},
            "sequence_num": self.sequence_num,
            "client_timestamp": int(self.current_time.timestamp() * 1000),
            "server_timestamp": self.current_time.isoformat()
        }

        self.events.append(event)
        return event

    def save_to_file(self, filename: str):
        """保存到JSON文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": self.session_id,
                "task_description": "撰写关于人工智能伦理的论文引言",
                "events": self.events
            }, f, ensure_ascii=False, indent=2)
        print(f"[OK] Generated {len(self.events)} events -> {filename}")


def generate_high_metacog_session() -> MockEventGenerator:
    """
    高元认知学生会话

    特征：
    - 先阅读任务说明（P4高）
    - 首次Prompt延迟60秒（P1高）
    - Prompt目标明确、有步骤拆解（P2/P3高）
    - AI回复后仔细阅读（M1高）
    - 频繁切换区域对比（M2高）
    - 多次追问和澄清（M3高）
    - AI回复后修改（E1高）
    - 深度编辑（E2高）
    - 验证行为多（E4高）
    """
    gen = MockEventGenerator()

    # 会话开始：先查看任务说明
    gen.generate_event(
        "page_view",
        "任务说明",
        {"duration": 120, "action": "open"},
        delay_seconds=5
    )

    # 思考60秒后发送第一个Prompt（目标明确、有拆解）
    gen.generate_event(
        "prompt",
        "请帮我构思一篇关于人工智能伦理的论文引言。具体要求：\n1. 先介绍AI技术发展背景\n2. 再提出伦理问题的重要性\n3. 最后说明本文的研究意义\n字数控制在300字左右。",
        {"source_area": "task"},
        delay_seconds=60
    )

    # AI回复
    gen.generate_event(
        "ai_reply",
        "近年来，人工智能技术迅猛发展，深度学习、大语言模型等技术突破使得AI在医疗、金融、教育等领域得到广泛应用...",
        {"source": "claude"},
        delay_seconds=3
    )

    # 仔细阅读AI回复（18秒）
    gen.generate_event(
        "focus_switch",
        "从对话区切换到任务区",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=18
    )

    # 追问澄清
    gen.generate_event(
        "prompt",
        "你提到的'深度学习技术突破'能否举一个具体例子？我想让读者更容易理解。",
        {"source_area": "task"},
        delay_seconds=5
    )

    # AI回复
    gen.generate_event(
        "ai_reply",
        "比如AlphaGo在2016年战胜围棋世界冠军李世石，这标志着深度强化学习在复杂决策问题上的突破...",
        {"source": "claude"},
        delay_seconds=2
    )

    # 阅读后切换到编辑区
    gen.generate_event(
        "focus_switch",
        "从对话区切换到任务区",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=12
    )

    # 验证AI提到的信息
    gen.generate_event(
        "verify",
        "查证AlphaGo战胜李世石的时间和背景资料",
        {"source_area": "task"},
        delay_seconds=30
    )

    # 编辑：深度加工AI内容
    gen.generate_event(
        "edit",
        "将AI提供的背景段落重新组织，调整论证逻辑，从技术发展→社会影响→伦理挑战的递进关系，并增加了过渡句",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=120
    )

    # 继续与AI对话完善内容
    gen.generate_event(
        "prompt",
        "伦理问题部分，我想强调'算法偏见'和'隐私保护'两个方向，请帮我补充这部分。",
        {"source_area": "task"},
        delay_seconds=20
    )

    gen.generate_event(
        "ai_reply",
        "算法偏见是AI伦理的核心问题之一。研究表明，由于训练数据的偏差，AI系统可能在性别、种族等方面表现出歧视性...",
        {"source": "claude"},
        delay_seconds=3
    )

    # 阅读并切换
    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=15
    )

    # 指出AI内容的不足
    gen.generate_event(
        "prompt",
        "这段关于算法偏见的描述太宽泛了，能否提供一个具体的案例？比如招聘AI或司法AI的案例。",
        {"source_area": "task"},
        delay_seconds=8
    )

    gen.generate_event(
        "ai_reply",
        "亚马逊曾在2018年放弃了一套AI招聘系统，因为该系统在筛选简历时表现出对女性候选人的系统性歧视...",
        {"source": "claude"},
        delay_seconds=2
    )

    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=10
    )

    # 验证案例真实性
    gen.generate_event(
        "verify",
        "搜索'亚马逊AI招聘系统偏见'相关新闻报道",
        {"source_area": "task"},
        delay_seconds=45
    )

    # 深度编辑：整合案例到论文中
    gen.generate_event(
        "edit",
        "将亚马逊案例整合到伦理问题段落，调整表述使其更学术化，并增加了对案例的反思：为什么会出现偏见？如何避免？",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=180
    )

    # 自主补充结尾
    gen.generate_event(
        "edit",
        "自己撰写了引言的结尾段落，说明本文的研究意义和创新点，没有使用AI生成",
        {"source_area": "task", "triggered_by_ai": False},
        delay_seconds=90
    )

    # 最后再验证一次整体逻辑
    gen.generate_event(
        "verify",
        "重新阅读整篇引言，检查论证逻辑是否连贯，是否符合任务要求",
        {"source_area": "task"},
        delay_seconds=60
    )

    return gen


def generate_low_metacog_session() -> MockEventGenerator:
    """
    低元认知学生会话

    特征：
    - 不看任务说明（P4低）
    - 首次Prompt延迟5秒（P1低）
    - Prompt目标模糊（P2低）
    - 无任务拆解（P3低）
    - AI回复后快速接受（M1低）
    - 几乎不切换区域（M2低）
    - 不追问（M3低）
    - 直接复制AI内容（E1低）
    - 仅表层修改（E2低）
    - 无验证行为（E4低）
    """
    gen = MockEventGenerator()

    # 会话开始，直接问AI（延迟5秒）
    gen.generate_event(
        "prompt",
        "帮我写一篇关于AI伦理的论文引言",
        {"source_area": "task"},
        delay_seconds=5
    )

    # AI回复
    gen.generate_event(
        "ai_reply",
        "随着人工智能技术的快速发展，AI伦理问题日益受到关注。本文将探讨AI技术在应用过程中面临的伦理挑战...",
        {"source": "claude"},
        delay_seconds=2
    )

    # 快速接受（3秒后就编辑）
    gen.generate_event(
        "edit",
        "直接复制AI生成的内容，仅修改了几个错别字",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=3
    )

    # 再次请求AI生成更多内容
    gen.generate_event(
        "prompt",
        "再写一段",
        {"source_area": "task"},
        delay_seconds=10
    )

    gen.generate_event(
        "ai_reply",
        "AI伦理涉及算法偏见、隐私保护、责任归属等多个方面。例如，算法偏见可能导致AI系统在决策中表现出不公平...",
        {"source": "claude"},
        delay_seconds=2
    )

    # 再次快速接受
    gen.generate_event(
        "edit",
        "复制粘贴，改了标点符号",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=4
    )

    # 第三次请求
    gen.generate_event(
        "prompt",
        "写个结尾",
        {"source_area": "task"},
        delay_seconds=8
    )

    gen.generate_event(
        "ai_reply",
        "因此，本文将系统分析AI伦理问题的现状与挑战，并探讨可行的解决方案，为AI技术的健康发展提供理论支持。",
        {"source": "claude"},
        delay_seconds=2
    )

    gen.generate_event(
        "edit",
        "复制粘贴，完成",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=2
    )

    return gen


def generate_mixed_metacog_session() -> MockEventGenerator:
    """
    中等元认知学生会话

    特征：
    - Planning中等：有一定思考但不够充分
    - Monitoring较弱：读得快，追问少
    - Evaluation中等：会修改但不够深入
    """
    gen = MockEventGenerator()

    # 简单看一下任务（30秒）
    gen.generate_event(
        "page_view",
        "任务说明",
        {"duration": 30, "action": "open"},
        delay_seconds=3
    )

    # 思考30秒后发Prompt（目标比较明确但无拆解）
    gen.generate_event(
        "prompt",
        "请帮我写一篇AI伦理论文的引言，要包括背景和研究意义，300字左右。",
        {"source_area": "task"},
        delay_seconds=30
    )

    gen.generate_event(
        "ai_reply",
        "近年来，人工智能技术迅猛发展，在医疗、教育、金融等领域得到广泛应用。然而，AI技术在带来便利的同时，也引发了诸多伦理问题...",
        {"source": "claude"},
        delay_seconds=3
    )

    # 阅读8秒（比低元认知强，但不如高元认知）
    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=8
    )

    # 编辑：中等深度（调整了部分内容）
    gen.generate_event(
        "edit",
        "调整了部分表述，增加了一句过渡，但整体结构未变",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=60
    )

    # 追问一次（但不够深入）
    gen.generate_event(
        "prompt",
        "能再补充一些关于算法偏见的内容吗？",
        {"source_area": "task"},
        delay_seconds=15
    )

    gen.generate_event(
        "ai_reply",
        "算法偏见是AI伦理的核心问题。由于训练数据可能存在偏差，AI系统在性别、种族等方面可能表现出歧视性...",
        {"source": "claude"},
        delay_seconds=2
    )

    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=6
    )

    # 编辑整合
    gen.generate_event(
        "edit",
        "将算法偏见的内容加入引言，调整了句子顺序",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=45
    )

    # 验证一次（比低元认知强）
    gen.generate_event(
        "verify",
        "检查了一下字数是否符合要求",
        {"source_area": "task"},
        delay_seconds=20
    )

    return gen


def generate_planning_weak_session() -> MockEventGenerator:
    """
    Planning弱但Monitoring/Evaluation强的会话
    用于测试干预优先级
    """
    gen = MockEventGenerator()

    # 直接问（P1低）
    gen.generate_event(
        "prompt",
        "写AI伦理引言",  # P2/P3低
        {"source_area": "task"},
        delay_seconds=3
    )

    gen.generate_event(
        "ai_reply",
        "AI伦理是当前研究的热点...",
        {"source": "claude"},
        delay_seconds=2
    )

    # 但后续表现出高Monitoring
    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=20  # M1高
    )

    gen.generate_event(
        "prompt",
        "这个说法太笼统了，能否给出具体的伦理问题？",  # M3/M4高
        {"source_area": "task"},
        delay_seconds=5
    )

    gen.generate_event(
        "ai_reply",
        "具体包括算法偏见、隐私泄露...",
        {"source": "claude"},
        delay_seconds=2
    )

    gen.generate_event(
        "focus_switch",
        "chat → task",
        {"from": "chat", "to": "task", "is_cross_area": True},
        delay_seconds=15
    )

    # 高Evaluation
    gen.generate_event(
        "verify",
        "查证算法偏见案例",
        {"source_area": "task"},
        delay_seconds=40
    )

    gen.generate_event(
        "edit",
        "大幅重写AI提供的内容，改变了论证结构",
        {"source_area": "task", "triggered_by_ai": True},
        delay_seconds=150
    )

    return gen


if __name__ == "__main__":
    from pathlib import Path

    # 确保输出目录存在
    output_dir = Path(__file__).parent / "mock_data"
    output_dir.mkdir(exist_ok=True)

    # 生成4种场景的模拟数据
    scenarios = [
        ("high_metacog", generate_high_metacog_session),
        ("low_metacog", generate_low_metacog_session),
        ("mixed_metacog", generate_mixed_metacog_session),
        ("planning_weak", generate_planning_weak_session)
    ]

    for name, generator_func in scenarios:
        gen = generator_func()
        gen.save_to_file(str(output_dir / f"{name}_session.json"))

    print("\n[OK] All mock data generated")
    print("\nExpected results:")
    print("  high_metacog: P/M/E > 0.7")
    print("  low_metacog: P/M/E < 0.4")
    print("  mixed_metacog: P/E ~0.5-0.6, M ~0.4")
    print("  planning_weak: P < 0.4 (should trigger Planning intervention), M/E > 0.6")
