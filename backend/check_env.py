"""
环境检查脚本 - 通义千问版本

运行此脚本检查系统配置是否正确，包括：
- Python 版本
- 依赖包安装情况
- 环境变量配置
- 阿里云百炼 API 连接测试
- 数据库连接测试

使用方法：
    python check_env.py
"""
import sys
import os

def check_python_version():
    """检查 Python 版本"""
    print("=" * 50)
    print("1. 检查 Python 版本")
    print("=" * 50)
    version = sys.version_info
    print(f"当前 Python 版本: {version.major}.{version.minor}.{version.micro}")

    if version.major == 3 and version.minor >= 11:
        print("✅ Python 版本符合要求 (>= 3.11)")
        return True
    else:
        print("❌ Python 版本过低，需要 >= 3.11")
        return False


def check_dependencies():
    """检查依赖包"""
    print("\n" + "=" * 50)
    print("2. 检查依赖包")
    print("=" * 50)

    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "aiosqlite",
        "pydantic",
        "openai",
        "numpy",
        "pandas",
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            missing.append(package)

    if missing:
        print(f"\n缺少以下依赖包: {', '.join(missing)}")
        print("请运行: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ 所有依赖包已安装")
        return True


def check_env_file():
    """检查环境变量文件"""
    print("\n" + "=" * 50)
    print("3. 检查环境变量文件")
    print("=" * 50)

    env_file = ".env"
    if not os.path.exists(env_file):
        print(f"❌ {env_file} 文件不存在")
        print("请运行: copy .env.example .env  # Windows")
        print("或运行: cp .env.example .env   # Mac/Linux")
        return False
    else:
        print(f"✅ {env_file} 文件存在")
        return True


def check_api_key():
    """检查 API Key 配置"""
    print("\n" + "=" * 50)
    print("4. 检查 API Key 配置")
    print("=" * 50)

    try:
        from app.config import settings

        api_key = settings.dashscope_api_key
        if not api_key or api_key == "你的API密钥请替换这里":
            print("❌ DASHSCOPE_API_KEY 未配置")
            print("请编辑 .env 文件，填写阿里云百炼 API Key")
            print("获取地址: https://bailian.console.aliyun.com/")
            return False
        else:
            # 隐藏密钥，只显示前缀和长度
            masked_key = api_key[:10] + "..." if len(api_key) > 10 else "***"
            print(f"✅ DASHSCOPE_API_KEY 已配置: {masked_key} (长度: {len(api_key)})")
            return True

    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return False


def check_api_connection():
    """测试 API 连接"""
    print("\n" + "=" * 50)
    print("5. 测试阿里云百炼 API 连接")
    print("=" * 50)

    try:
        from openai import OpenAI
        from app.config import settings

        client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )

        print("正在测试 API 连接...")

        response = client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=10,
        )

        reply = response.choices[0].message.content
        print(f"✅ API 连接成功")
        print(f"模型: {settings.chat_model}")
        print(f"测试回复: {reply}")
        return True

    except Exception as e:
        print(f"❌ API 连接失败: {e}")
        print("\n可能的原因:")
        print("1. API Key 无效")
        print("2. 余额不足")
        print("3. 网络连接问题")
        print("4. 模型名称错误")
        return False


def check_database():
    """检查数据库配置"""
    print("\n" + "=" * 50)
    print("6. 检查数据库配置")
    print("=" * 50)

    try:
        from app.config import settings

        db_url = settings.database_url
        print(f"数据库 URL: {db_url}")

        if "sqlite" in db_url:
            print("✅ 使用 SQLite 数据库（无需额外配置）")

            # 检查数据库文件
            db_file = db_url.split("///")[-1]
            if os.path.exists(db_file):
                print(f"✅ 数据库文件已存在: {db_file}")
            else:
                print(f"ℹ️  数据库文件将在首次启动时自动创建: {db_file}")

            return True
        else:
            print("ℹ️  使用外部数据库（PostgreSQL 等）")
            print("请确保数据库服务已启动")
            return True

    except Exception as e:
        print(f"❌ 数据库配置检查失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "🔍 元认知自适应学习系统 - 环境检查".center(50))
    print("\n")

    results = []

    # 执行所有检查
    results.append(("Python 版本", check_python_version()))
    results.append(("依赖包", check_dependencies()))
    results.append(("环境变量文件", check_env_file()))
    results.append(("API Key 配置", check_api_key()))
    results.append(("API 连接测试", check_api_connection()))
    results.append(("数据库配置", check_database()))

    # 汇总结果
    print("\n" + "=" * 50)
    print("检查结果汇总")
    print("=" * 50)

    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n" + "🎉 环境检查通过！".center(50))
        print("\n下一步:")
        print("1. 启动后端: uvicorn main:app --reload")
        print("2. 启动前端: cd ../frontend && npm run dev")
        print("3. 访问: http://localhost:5173")
    else:
        print("\n" + "⚠️  环境检查未通过，请修复上述问题".center(50))
        print("\n需要帮助？")
        print("- 查看 README.md")
        print("- 查看 QUICKSTART.md")

    print("\n")


if __name__ == "__main__":
    main()
