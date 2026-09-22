"""Cross-check completed browser sessions against real SQLite and exported files."""

import json
from pathlib import Path

from common import ROOT, bootstrap

bootstrap()

from app.services.core import Core  # noqa: E402
from app.services.exporting import backup, export_session, restore, validate_export  # noqa: E402
from app.settings import Settings  # noqa: E402


def main():
    run = json.loads((ROOT / "artifacts/e2e-current.json").read_text(encoding="utf-8"))
    data = Path(run["data_dir"])
    core = Core(Settings(data_dir=data, database=data / "app.db", secret="audit" * 10, env="test"))
    output = data / "audit"
    output.mkdir(exist_ok=True)
    reports = []
    with core.db.read() as conn:
        sessions = [dict(row) for row in conn.execute("SELECT * FROM sessions ORDER BY started_at")]
        all_events = [
            dict(row)
            for row in conn.execute("SELECT * FROM events ORDER BY session_id,sequence_no")
        ]
    for session in sessions:
        destination = output / f"{session['id']}.zip"
        export_session(core, session["id"], destination)
        reports.append(
            {
                "session_id": session["id"],
                "seat_no": session["seat_no"],
                "status": session["status"],
                **validate_export(destination),
            }
        )
    video_events = [
        json.loads(e["payload_json"]) for e in all_events if e["event_name"] == "example_closed"
    ]
    assert video_events and video_events[0]["watched_seconds"] >= 1, "未记录真实播放"
    assert video_events[1]["watched_seconds"] < 0.2, "重开暂停期间不应增加观看时长"
    assert abs(video_events[0]["last_position_sec"] - video_events[1]["last_position_sec"]) < 0.5
    names = sorted({e["event_name"] for e in all_events})
    expected = {
        json.loads(line)["event_id"]
        for line in (data / "expected-client-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    actual = {event["event_id"] for event in all_events}
    assert not expected - actual, "仍有浏览器发出的合法事件未落库"
    archive = output / "backup.zip"
    backup(core, archive)
    restored = restore(archive, data.parent / (data.name + "-restored"))
    report = {
        "sessions": reports,
        "event_names": names,
        "event_count": len(all_events),
        "video_checks": "passed",
        "restore": restored,
        "all_sessions_ended": all(s["status"] == "ENDED" for s in sessions),
        "expected_client_event_ids": sorted(expected),
        "missing_client_event_ids": sorted(expected - actual),
        "client_delivery_rate": 1.0,
    }
    (ROOT / "artifacts/data-quality-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "sessions": len(reports),
                "event_count": len(all_events),
                "event_types": len(names),
                "verified_edit_events": sum(r["verified_edit_events"] for r in reports),
                "export_and_restore": "passed",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
