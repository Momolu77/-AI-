import json
import sqlite3
from contextlib import closing, contextmanager

from app.settings import ROOT

TABLES = {
    "attachments",
    "ai_requests",
    "ai_responses",
    "preview_runs",
    "preview_logs",
    "submissions",
    "snapshots",
    "code_revisions",
    "planner_revisions",
}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Database:
    def __init__(self, path):
        self.path = path

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
                version = int(migration.name.split("_", 1)[0])
                if version in applied:
                    continue
                conn.executescript(migration.read_text(encoding="utf-8"))
                conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES(?)", (version,))
                conn.commit()

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def get(conn, table, object_id, session_id=None):
        assert table in TABLES
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (object_id,)).fetchone()
        if row is None or (session_id is not None and row["session_id"] != session_id):
            return None
        return {"id": row["id"], "session_id": row["session_id"], **json.loads(row["body"])}

    @staticmethod
    def all(conn, table, session_id):
        assert table in TABLES
        return [
            {"id": row["id"], "session_id": row["session_id"], **json.loads(row["body"])}
            for row in conn.execute(
                f"SELECT * FROM {table} WHERE session_id=? ORDER BY rowid", (session_id,)
            )
        ]

    @staticmethod
    def put(conn, table, object_id, session_id, body, revision_no=None):
        assert table in TABLES
        if revision_no is not None:
            conn.execute(
                f"INSERT INTO {table}(id,session_id,revision_no,body) VALUES(?,?,?,?)",
                (object_id, session_id, revision_no, encode(body)),
            )
        else:
            conn.execute(
                f"INSERT INTO {table}(id,session_id,body) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body WHERE {table}.session_id=excluded.session_id",
                (object_id, session_id, encode(body)),
            )

    @staticmethod
    def session(conn, session_id):
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
