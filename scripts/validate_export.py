import argparse
import json

import common  # noqa: F401
from app.services.exporting import validate_export

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    print(json.dumps(validate_export(args.input), ensure_ascii=False, indent=2))
