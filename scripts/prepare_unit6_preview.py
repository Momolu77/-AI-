"""Add an engineering preview task to local seats without replacing existing sessions."""

import argparse
import json

from common import ROOT, load_core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    args = parser.parse_args()
    core = load_core(args.env_file)
    if core.settings.env != "local":
        raise ValueError("此脚本仅用于本地工程预览，不发布正式采集任务")
    task = json.loads((ROOT / "config/task-templates/unit6.json").read_text(encoding="utf-8"))
    task.update(
        task_id="unit6-preview",
        publication_status="engineering_preview",
    )
    core.collection.publish(task)
    from app.repositories.database import encode
    from app.services.core import uid

    with core.db.transaction() as conn:
        conn.execute(
            "INSERT INTO task_configs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
            (task["task_id"], encode(task)),
        )
    tokens = core.seed()
    with core.db.transaction() as conn:
        for row in conn.execute("SELECT participant_id FROM seat_participants").fetchall():
            conn.execute(
                "INSERT OR IGNORE INTO task_assignments VALUES(?,?,?,?)",
                (uid(), row[0], task["task_id"], "engineering-preview"),
            )
    print("已添加 Unit 6 工程试用任务；原会话和数据保留。")
    print("当前任务未结束时，先保存作品并提交或结束，再回到任务列表选择工程试用。")
    print(f"AI 模式：{core.settings.ai_provider}；正式采集任务仍为草稿。")
    for seat, token in tokens.items():
        print(f"座位 {seat}: http://127.0.0.1:5173/enter?seat={seat}&token={token}")


if __name__ == "__main__":
    main()
