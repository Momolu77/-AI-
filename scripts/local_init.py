import argparse
import secrets
from pathlib import Path

from common import ROOT, load_core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    args = parser.parse_args()
    env = Path(args.env_file).resolve()
    if not env.exists():
        env.write_text((ROOT / ".env.local.example").read_text(encoding="utf-8"), encoding="utf-8")
    text = env.read_text(encoding="utf-8")
    if "JWT_SECRET=\n" in text or text.endswith("JWT_SECRET="):
        env.write_text(
            text.replace("JWT_SECRET=", "JWT_SECRET=" + secrets.token_urlsafe(48), 1),
            encoding="utf-8",
        )
    core = load_core(env)
    print(f"本地数据库已初始化：{core.settings.database}")


if __name__ == "__main__":
    main()
