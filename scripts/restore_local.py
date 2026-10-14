import argparse
import json

import common  # noqa: F401
from app.services.exporting import restore

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--restrictions-file", help="研究者现行停止/排除账本；恢复到其他目录时必须沿用并配置此路径"
    )
    args = parser.parse_args()
    print(json.dumps(restore(args.input, args.target, args.restrictions_file), ensure_ascii=False))
