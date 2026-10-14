"""Assign an anonymous research ID to a seat and task, without combining seat occupants."""

import argparse
import json
import secrets

from common import bootstrap, load_core

bootstrap()
from app.services.core import uid  # noqa: E402
from app.services.files import atomic_write, digest  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--seat", required=True)
parser.add_argument("--participant-id", required=True)
parser.add_argument("--task-id", required=True)
parser.add_argument("--condition-id", default="default")
parser.add_argument("--env-file", default=".env.local")
args = parser.parse_args()
core = load_core(args.env_file)
with core.db.transaction() as conn:
    if conn.execute(
        "SELECT 1 FROM sessions WHERE (seat_no=? OR participant_id=?) AND status IN ('PREPARING','ACTIVE','ENDING')",
        (args.seat, args.participant_id),
    ).fetchone():
        raise ValueError("请先结束原来的活动会话，再重新分配座位")
    if not conn.execute("SELECT 1 FROM task_configs WHERE id=?", (args.task_id,)).fetchone():
        raise ValueError("任务尚未发布")
    token = secrets.token_urlsafe(24)
    from datetime import timedelta

    conn.execute(
        "INSERT INTO seats VALUES(?,?,?,?) ON CONFLICT(seat_no) DO UPDATE SET token_hash=excluded.token_hash,task_id=excluded.task_id,expires_at=excluded.expires_at",
        (args.seat, digest(token), args.task_id, (core.clock() + timedelta(days=365)).isoformat()),
    )
    conn.execute(
        "INSERT OR IGNORE INTO participants VALUES(?,?)", (args.participant_id, core.now())
    )
    conn.execute(
        "INSERT INTO seat_participants VALUES(?,?) ON CONFLICT(seat_no) DO UPDATE SET participant_id=excluded.participant_id",
        (args.seat, args.participant_id),
    )
    conn.execute(
        "INSERT INTO task_assignments VALUES(?,?,?,?) ON CONFLICT(participant_id,task_id) DO UPDATE SET condition_id=excluded.condition_id",
        (uid(), args.participant_id, args.task_id, args.condition_id),
    )

token_file = core.settings.data_dir / "seat-tokens.json"
tokens = json.loads(token_file.read_text(encoding="utf-8")) if token_file.exists() else {}
tokens[args.seat] = token
atomic_write(token_file, json.dumps(tokens))
print(f"/enter?seat={args.seat}&token={token}")
