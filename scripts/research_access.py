"""Stop collection and prepare a restricted handling inventory; never silently erase files."""

import argparse
import json

from common import ROOT, load_core

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--mode", choices=["inventory", "stop", "exclude"], default="inventory")
    parser.add_argument("--reason")
    parser.add_argument("--policy-version")
    args = parser.parse_args()
    core = load_core(args.env_file)
    if args.mode != "inventory":
        if not args.reason or not args.policy_version:
            parser.error("停止或排除必须提供 --reason 与 --policy-version")
        core.research_access.stop(
            args.participant_id, args.reason, args.policy_version, args.mode == "exclude"
        )
    print(json.dumps(core.research_access.inventory(args.participant_id), ensure_ascii=False))
