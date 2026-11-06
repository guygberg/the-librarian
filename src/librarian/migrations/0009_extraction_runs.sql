-- One row per extraction call, plus the pieces the validator dropped. Raw envelopes are kept for tracing.
CREATE TABLE extraction_runs (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    unit_key TEXT NOT NULL,
    model TEXT NOT NULL,
    claude_code_version TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    envelope TEXT NOT NULL,
    accepted INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE extraction_rejections (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    run_id INTEGER NOT NULL REFERENCES extraction_runs(id),
    piece TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX extraction_rejections_run ON extraction_rejections (run_id);
