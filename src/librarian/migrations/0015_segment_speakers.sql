-- Who spoke a transcript segment, set by hand. Keyed by the recording path and the segment's time span, not by Source
-- item: a re-transcription (new file hash, new Source items) finds the setting again by time overlap.
CREATE TABLE segment_speakers (
    workspace TEXT NOT NULL,
    path TEXT NOT NULL,
    start REAL NOT NULL,
    "end" REAL NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    at TEXT NOT NULL,
    PRIMARY KEY (workspace, path, start, "end")
);
