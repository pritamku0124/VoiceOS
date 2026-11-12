-- VoiceOS local database (SQLite). Created automatically on first run.
-- Everything stays on this computer: database\voiceos.db (git-ignored).

CREATE TABLE IF NOT EXISTS command_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,              -- ISO date-time, local time
    input_text  TEXT    NOT NULL,              -- what was said or typed
    input_mode  TEXT    NOT NULL DEFAULT 'voice', -- 'voice' or 'typed'
    source      TEXT    NOT NULL,              -- who understood it: 'rules', 'ai' or 'none'
    intents     TEXT    NOT NULL DEFAULT '[]', -- JSON list of {"action", "params", "status"}
    reply       TEXT    NOT NULL DEFAULT '',   -- what VoiceOS answered
    status      TEXT    NOT NULL               -- 'done', 'planned', 'failed', 'answered', 'not_understood'
);

CREATE INDEX IF NOT EXISTS idx_history_created ON command_history (created_at);
