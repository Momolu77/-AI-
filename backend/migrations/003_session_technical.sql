CREATE TABLE session_technical(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), body TEXT NOT NULL);
INSERT OR IGNORE INTO participants(id,created_at) SELECT participant_id,MIN(created_at) FROM sessions GROUP BY participant_id;
