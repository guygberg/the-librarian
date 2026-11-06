-- `forget` deletes Records, and the Person event that records the forgetting must outlive them. So an event may
-- have no Record (record_id NULL, no foreign key), and the events of a Record that no longer exists may be deleted.
CREATE TABLE record_events_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    record_id INTEGER,
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    at TEXT NOT NULL
);
INSERT INTO record_events_new SELECT id, workspace, record_id, event, detail, at FROM record_events;
DROP TABLE record_events;
ALTER TABLE record_events_new RENAME TO record_events;
CREATE INDEX record_events_record ON record_events (workspace, record_id);

CREATE TRIGGER record_events_no_update BEFORE UPDATE ON record_events
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;

CREATE TRIGGER record_events_no_delete BEFORE DELETE ON record_events
WHEN OLD.record_id IS NULL OR EXISTS (SELECT 1 FROM records WHERE id = OLD.record_id)
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;
