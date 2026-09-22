import argparse
import json

import common  # noqa: F401
from app.services.exporting import restore

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.input, args.target), ensure_ascii=False))
