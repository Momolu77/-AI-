"""Import a researcher JSON bundle or a folder of documented CSV/JSONL tables."""

import argparse
import csv
import json
from pathlib import Path

from common import bootstrap, load_core

bootstrap()
from app.services.capture import CaptureService  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("input", type=Path)
parser.add_argument("--env-file", default=".env.local")
parser.add_argument(
    "--ffprobe", help="ffprobe executable; unavailable media remains explicitly unverified"
)
args = parser.parse_args()
if args.input.is_dir():
    bundle = {}
    numeric = {
        "segment",
        "duration_ms",
        "width",
        "height",
        "frame_rate",
        "video_start_ms",
        "video_end_ms",
        "video_pts_ms",
        "estimated_error_ms",
        "score",
    }
    for path in args.input.glob("*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            for key in row:
                if row[key] == "":
                    row[key] = None
                elif key == "known_gaps":
                    row[key] = json.loads(row[key])
                elif key in numeric:
                    row[key] = float(row[key])
        bundle[path.stem] = rows
    markers = args.input / "capture_events.jsonl"
    if markers.exists():
        bundle["capture_events"] = [
            json.loads(line) for line in markers.read_text(encoding="utf-8").splitlines() if line
        ]
    clocks = args.input / "clock_calibrations.json"
    if clocks.exists():
        bundle["clock_calibrations"] = json.loads(clocks.read_text(encoding="utf-8"))
    base = args.input
else:
    bundle = json.loads(args.input.read_text(encoding="utf-8"))
    base = args.input.parent
print(
    json.dumps(
        CaptureService(load_core(args.env_file), args.ffprobe).import_bundle(bundle, base),
        ensure_ascii=False,
        indent=2,
    )
)
