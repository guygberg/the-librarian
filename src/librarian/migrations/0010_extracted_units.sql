-- A unit whose result was persisted. The hash of the text sent lets a changed unit be extracted again.
CREATE TABLE extracted_units (
    workspace TEXT NOT NULL,
    unit_key TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    PRIMARY KEY (workspace, unit_key)
);
