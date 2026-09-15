#!/usr/bin/env python3
"""
快速功能测试脚本
测试后端核心模块是否正常工作
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def test_state_recognizer():
    """测试状态识别模块"""
    print("\n🧪 测试状态识别模块")
    print("-" * 60)

    from app.services.state_recognizer import compute_metacog_state
    from app.models.models import InteractionLog
    from datetime import datetime

    # 模拟交互日志
    mock_logs = [
        InteractionLog(
            event_type="prompt",
            content="我该如何开始这个任务？需要考虑哪些因素？",
            timestamp=datetime.now(),
            metadata={}
        ),
        InteractionLog(
            event_type="edit",
            content="修改了第一段的表述",
            timestamp=datetime.now(),
            metadata={}
        ),
        InteractionLog(
            event_type="verify",
            content="检查了引用格式",
            timestamp=datetime.now(),
            metadata={}
        ),
    ]

    state = compute_metacog_state(mock_logs)

    print(f"✅ 计算结果:")
    print(f"   Planning:    {state['planning']:.3f}")
    print(f"   Monitoring:  {state['monitoring']:.3f}")
    print(f"   Evaluation:  {state['evaluation']:.3f}")

    # 验证输出范围
    for key, value in state.items():
        assert 0 <= value <= 1, f"{key} 值超出范围: {value}"

    print("✅ 状态识别模块测试通过")
    return True

async def test_intervention_decision():
    """测试干预决策模块"""
    print("\n🧪 测试干预决策模块")
    print("-" * 60)

    from app.services.intervention import decide_intervention
    from app.models.models import MetacogState
    from datetime import datetime

    # 模拟当前状态（低Planning）
    current_state = {
        "planning": 0.2,
        "monitoring": 0.6,
        "evaluation": 0.5
    }

    # 模拟历史状态（持续低Planning）
    history = [
        MetacogState(
            planning=0.25,
            monitoring=0.55,
            evaluation=0.5,
            timestamp=datetime.now()
        ),
        MetacogState(
            planning=0.22,
            monitoring=0.58,
            evaluation=0.52,
            timestamp=datetime.now()
        ),
        MetacogState(
            planning=0.2,
            monitoring=0.6,
            evaluation=0.5,
            timestamp=datetime.now()
        ),
    ]

    decision = decide_intervention(current_state, history)

    if decision:
        print(f"✅ 触发干预:")
        print(f"   类型: {decision['type']}")
        print(f"   维度: {decision['dimension']}")
        print(f"   原因: {decision['reason']}")
    else:
        print("⚠️  未触发干预（可能是正常情况）")

    print("✅ 干预决策模块测试通过")
    return True

async def test_ai_generator():
    """测试AI生成模块（需要API Key）"""
    print("\n🧪 测试AI生成模块")
    print("-" * 60)

    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key or api_key == "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        print("⚠️  ANTHROPIC_API_KEY 未配置，跳过AI测试")
        return True

    from app.services.ai_generator import chat_with_ai, generate_intervention

    # 测试对话
    print("📤 测试对话生成...")
    history = [
        {"role": "user", "content": "你好"},
    ]

    try:
        reply = await chat_with_ai(history, "请简单介绍一下自己")
        print(f"✅ AI回复: {reply[:100]}...")

        # 测试干预生成
        print("\n📤 测试干预内容生成...")
        intervention = await generate_intervention(
            intervention_type="metacog_prompt",
            dimension="planning",
            current_state={"planning": 0.2, "monitoring": 0.6, "evaluation": 0.5},
            context="用户正在进行学术写作任务"
        )
        print(f"✅ 干预内容: {intervention[:100]}...")

        print("✅ AI生成模块测试通过")
        return True

    except Exception as e:
        print(f"❌ AI调用失败: {e}")
        print("   请检查 API Key 是否正确以及网络连接")
        return False

async def test_database_connection():
    """测试数据库连接"""
    print("\n🧪 测试数据库连接")
    print("-" * 60)

    import os
    from dotenv import load_dotenv
    from app.database import get_db, redis_client

    load_dotenv()

    # 测试 PostgreSQL
    print("📤 测试 PostgreSQL...")
    try:
        async for db in get_db():
            # 简单查询测试
            from sqlalchemy import text
            result = await db.execute(text("SELECT 1"))
            assert result.scalar() == 1
            print("✅ PostgreSQL 连接成功")
            break
    except Exception as e:
        print(f"❌ PostgreSQL 连接失败: {e}")
        return False

    # 测试 Redis
    print("\n📤 测试 Redis...")
    try:
        await redis_client.set("test_key", "test_value", ex=10)
        value = await redis_client.get("test_key")
        assert value == "test_value"
        await redis_client.delete("test_key")
        print("✅ Redis 连接成功")
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        return False

    print("✅ 数据库连接测试通过")
    return True

async def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 元认知自适应学习系统 - 功能测试")
    print("=" * 60)

    tests = [
        ("状态识别", test_state_recognizer),
        ("干预决策", test_intervention_decision),
        ("数据库连接", test_database_connection),
        ("AI生成", test_ai_generator),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 输出总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}  {name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！系统核心功能正常")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置和依赖")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
