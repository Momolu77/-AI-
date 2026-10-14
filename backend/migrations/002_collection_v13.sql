PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
CREATE TABLE sessions_v13(
 id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, seat_no TEXT NOT NULL,
 task_id TEXT NOT NULL, task_version TEXT NOT NULL, task_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PREPARING','ACTIVE','ENDING','ENDED','ABANDONED')),
 started_at TEXT, last_seen_at TEXT NOT NULL, ended_at TEXT,
 next_sequence INTEGER NOT NULL DEFAULT 1,
 schema_version TEXT NOT NULL DEFAULT 'teaching-workbench-events-v1.3',
 created_at TEXT NOT NULL, prerequisite_json TEXT,
 writer_id TEXT, lease_until TEXT, detach_at TEXT, detach_persisted INTEGER NOT NULL DEFAULT 0
);
INSERT INTO sessions_v13(id,participant_id,seat_no,task_id,task_version,task_json,status,started_at,last_seen_at,ended_at,next_sequence,schema_version,created_at)
SELECT id,participant_id,seat_no,task_id,task_version,task_json,status,started_at,last_seen_at,ended_at,next_sequence,'teaching-workbench-events-v1.1',started_at FROM sessions;
DROP TABLE sessions;
ALTER TABLE sessions_v13 RENAME TO sessions;
CREATE UNIQUE INDEX one_active_seat ON sessions(seat_no) WHERE status IN ('PREPARING','ACTIVE','ENDING');
CREATE UNIQUE INDEX one_active_participant ON sessions(participant_id) WHERE status IN ('PREPARING','ACTIVE','ENDING');
CREATE TABLE participants(id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE seat_participants(seat_no TEXT PRIMARY KEY REFERENCES seats(seat_no), participant_id TEXT NOT NULL REFERENCES participants(id));
CREATE TABLE task_assignments(id TEXT PRIMARY KEY, participant_id TEXT NOT NULL REFERENCES participants(id), task_id TEXT NOT NULL REFERENCES task_configs(id), condition_id TEXT NOT NULL DEFAULT 'default', UNIQUE(participant_id,task_id));
CREATE TABLE event_transport(event_id TEXT PRIMARY KEY REFERENCES events(event_id), schema_version TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE clock_calibrations(id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE resources(id TEXT NOT NULL, version TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(id,version));
CREATE TABLE resource_references(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE request_drafts(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE draft_revisions(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE ai_response_chunks(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE ai_proposals(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE proposal_applications(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
CREATE TABLE capture_records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, participant_id TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE capture_events(event_id TEXT PRIMARY KEY, recording_id TEXT NOT NULL, participant_id TEXT NOT NULL, capture_sequence_no INTEGER NOT NULL, body TEXT NOT NULL, UNIQUE(recording_id,capture_sequence_no));
CREATE TABLE recording_sessions(recording_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(id), video_start_ms REAL NOT NULL, video_end_ms REAL NOT NULL, PRIMARY KEY(recording_id,session_id,video_start_ms));
INSERT OR IGNORE INTO schema_migrations VALUES(2);
COMMIT;
PRAGMA foreign_keys=ON;
