import argparse
import json

from common import ROOT, bootstrap, load_core

bootstrap()

from app.services.exporting import export_session  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = export_session(load_core(args.env_file), args.session_id, args.output)
    print(json.dumps(result["quality"], ensure_ascii=False, indent=2))
