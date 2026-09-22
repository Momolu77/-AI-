import argparse

from common import ROOT, bootstrap, load_core

bootstrap()

from app.services.exporting import backup  # noqa: E402
from app.services.locking import data_lock  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="先停止本地后端再备份，确保数据库和作品文件处于同一稳定状态。"
    )
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    core = load_core(args.env_file)
    with data_lock(core.settings.data_dir):
        backup(core, args.output)
    print("备份完成（含座位入口，请保存在本机）。")
