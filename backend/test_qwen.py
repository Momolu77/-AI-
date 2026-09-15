"""
快速测试通义千问 API

这个脚本独立运行，不依赖项目其他模块，用于快速验证 API Key 是否有效。

使用方法：
    python test_qwen.py
"""
import os
from openai import OpenAI

# 从 .env 文件读取 API Key
def load_api_key():
    """读取 .env 文件中的 API Key"""
    env_file = ".env"
    if not os.path.exists(env_file):
        print("❌ .env 文件不存在")
        return None

    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('DASHSCOPE_API_KEY='):
                key = line.split('=', 1)[1].strip()
                if key and key != "你的API密钥请替换这里":
                    return key

    print("❌ .env 文件中未找到有效的 DASHSCOPE_API_KEY")
    return None


def test_chat():
    """测试主对话接口（qwen3.8-flash）"""
    print("\n" + "=" * 60)
    print("测试 1: 主对话接口 (qwen3.8-flash)")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        return False

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        print("发送消息: 你好，请用一句话介绍你自己")

        response = client.chat.completions.create(
            model="qwen3.8-flash",
            messages=[{"role": "user", "content": "你好，请用一句话介绍你自己"}],
            extra_body={"enable_thinking": False},  # 关闭思考模式
            stream=False,
        )

        reply = response.choices[0].message.content
        usage = response.usage

        print(f"\n✅ API 调用成功")
        print(f"回复: {reply}")
        print(f"\nToken 用量:")
        print(f"  - 输入: {usage.prompt_tokens} tokens")
        print(f"  - 输出: {usage.completion_tokens} tokens")
        print(f"  - 总计: {usage.total_tokens} tokens")
        print(f"请求 ID: {response.id}")

        return True

    except Exception as e:
        print(f"\n❌ API 调用失败")
        print(f"错误信息: {str(e)}")
        print("\n可能的原因:")
        print("1. API Key 无效或过期")
        print("2. 账户余额不足")
        print("3. 网络连接问题")
        print("4. 模型名称错误")
        return False


def test_streaming():
    """测试流式输出"""
    print("\n" + "=" * 60)
    print("测试 2: 流式输出 (qwen3.8-flash)")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        return False

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        print("发送消息: 用三个词描述春天")
        print("回复: ", end="", flush=True)

        stream = client.chat.completions.create(
            model="qwen3.8-flash",
            messages=[{"role": "user", "content": "用三个词描述春天"}],
            extra_body={"enable_thinking": False},
            stream=True,
        )

        full_reply = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_reply += content

        print("\n\n✅ 流式输出测试成功")
        print(f"完整回复: {full_reply}")

        return True

    except Exception as e:
        print(f"\n\n❌ 流式输出测试失败")
        print(f"错误信息: {str(e)}")
        return False


def test_judge_model():
    """测试判断模型（qwen3.7-flash）"""
    print("\n" + "=" * 60)
    print("测试 3: 判断模型 (qwen3.7-flash)")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        return False

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        print("发送消息: 判断情感（积极/消极）：'今天天气真好'")

        response = client.chat.completions.create(
            model="qwen3.7-flash",
            messages=[
                {"role": "system", "content": "你是一个情感分析助手，只回复'积极'或'消极'"},
                {"role": "user", "content": "判断以下句子的情感：'今天天气真好'"}
            ],
            temperature=0,  # 温度设为0，确保输出一致
            extra_body={"enable_thinking": False},
            stream=False,
        )

        reply = response.choices[0].message.content

        print(f"\n✅ 判断模型调用成功")
        print(f"回复: {reply}")

        return True

    except Exception as e:
        print(f"\n❌ 判断模型调用失败")
        print(f"错误信息: {str(e)}")
        return False


def main():
    """主函数"""
    print("\n" + "🧪 通义千问 API 测试".center(60))
    print("\n")

    results = []

    # 执行所有测试
    results.append(("主对话接口", test_chat()))
    results.append(("流式输出", test_streaming()))
    results.append(("判断模型", test_judge_model()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n" + "🎉 所有测试通过！API 配置正确".center(60))
        print("\n下一步:")
        print("1. 运行完整环境检查: python check_env.py")
        print("2. 启动后端: uvicorn main:app --reload")
    else:
        print("\n" + "⚠️  部分测试失败，请检查 API Key 配置".center(60))
        print("\n排查建议:")
        print("1. 确认 .env 中 DASHSCOPE_API_KEY 已正确填写")
        print("2. 访问 https://bailian.console.aliyun.com/ 检查余额")
        print("3. 确认网络连接正常")

    print("\n")


if __name__ == "__main__":
    main()
