-- Person events on a Record: append-only; re-extraction never touches them. The current view applies them in order.
CREATE TABLE record_events (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    record_id INTEGER NOT NULL REFERENCES records(id),
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    at TEXT NOT NULL
);
CREATE INDEX record_events_record ON record_events (workspace, record_id);

CREATE TRIGGER record_events_no_update BEFORE UPDATE ON record_events
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;

CREATE TRIGGER record_events_no_delete BEFORE DELETE ON record_events
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;

-- The Records the latest extraction of each unit produced. A Record with no row here is no longer found in sources.
CREATE TABLE unit_records (
    workspace TEXT NOT NULL,
    unit_key TEXT NOT NULL,
    record_id INTEGER NOT NULL REFERENCES records(id),
    PRIMARY KEY (workspace, unit_key, record_id)
);
CREATE INDEX unit_records_record ON unit_records (workspace, record_id);

-- Two Records that contradict each other: one row, shown from both sides.
CREATE TABLE links_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'belongs_to', 'owner', 'waiting_on', 'blocks', 'supersedes',
        'related_to', 'mentions', 'evidence', 'contradicts')),
    from_type TEXT NOT NULL CHECK (from_type IN ('record', 'person', 'source_item')),
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL CHECK (to_type IN ('record', 'person', 'source_item')),
    to_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace, type, from_type, from_id, to_type, to_id)
);
INSERT INTO links_new SELECT * FROM links;
DROP TABLE links;
ALTER TABLE links_new RENAME TO links;
CREATE INDEX links_to ON links (workspace, to_type, to_id);
