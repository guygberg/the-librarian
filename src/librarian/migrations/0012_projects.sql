-- Review entries for projects. `other_record_id` is the existing project a suggestion points at.
CREATE TABLE review_entries_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'unconfirmed_person', 'unknown_speaker', 'inferred_project', 'suggested_project', 'merge_project')),
    record_id INTEGER NOT NULL REFERENCES records(id),
    link_type TEXT NOT NULL,
    raw_name TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    other_record_id INTEGER REFERENCES records(id)
);
INSERT INTO review_entries_new (id, workspace, kind, record_id, link_type, raw_name, created_at, resolved_at)
    SELECT id, workspace, kind, record_id, link_type, raw_name, created_at, resolved_at FROM review_entries;
DROP TABLE review_entries;
ALTER TABLE review_entries_new RENAME TO review_entries;
CREATE INDEX review_entries_record ON review_entries (workspace, record_id);

-- Other names a project is known by; a name that equals one links to the project automatically.
CREATE TABLE project_aliases (
    workspace TEXT NOT NULL,
    record_id INTEGER NOT NULL REFERENCES records(id),
    alias TEXT NOT NULL,
    PRIMARY KEY (workspace, record_id, alias)
);
