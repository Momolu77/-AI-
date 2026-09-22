CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS task_configs(id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seats(seat_no TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, seat_no TEXT NOT NULL,
 task_id TEXT NOT NULL, task_version TEXT NOT NULL, task_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ACTIVE','ENDED')),
 started_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, ended_at TEXT,
 next_sequence INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_seat ON sessions(seat_no) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS events(
 event_id TEXT PRIMARY KEY, event_name TEXT NOT NULL,
 actor TEXT NOT NULL CHECK(actor IN ('student','system')),
 session_id TEXT NOT NULL REFERENCES sessions(id), participant_id TEXT NOT NULL,
 task_id TEXT NOT NULL, seat_no TEXT NOT NULL, occurred_at TEXT NOT NULL,
 recorded_at TEXT NOT NULL, sequence_no INTEGER NOT NULL, client_sequence_no INTEGER,
 payload_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
 UNIQUE(session_id,sequence_no)
);
CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
CREATE TABLE IF NOT EXISTS code_revisions(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), revision_no INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(session_id,revision_no));
CREATE TABLE IF NOT EXISTS planner_revisions(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), revision_no INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(session_id,revision_no));
CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_requests(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_responses(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preview_runs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preview_logs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
INSERT OR IGNORE INTO schema_migrations VALUES(1);
