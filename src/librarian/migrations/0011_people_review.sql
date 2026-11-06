-- "Me" is one Person; Slack-login and configured names are Aliases of it.
ALTER TABLE persons ADD COLUMN is_me INTEGER NOT NULL DEFAULT 0;

-- Two Persons may carry the same Alias (two people called Dana); the name is then ambiguous and never auto-links.
CREATE TABLE aliases_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    alias TEXT NOT NULL,
    UNIQUE (workspace, person_id, alias)
);
INSERT INTO aliases_new (id, workspace, person_id, alias) SELECT id, workspace, person_id, alias FROM aliases;
DROP TABLE aliases;
ALTER TABLE aliases_new RENAME TO aliases;
CREATE INDEX aliases_alias ON aliases (workspace, alias);

-- Suggested links: a name that could not be linked with certainty. The Record keeps no owner/Link row for it, so
-- confirmed ownership (a Record column or Link) and suggested ownership (a row here) never mix.
CREATE TABLE review_entries (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('unconfirmed_person', 'unknown_speaker')),
    record_id INTEGER NOT NULL REFERENCES records(id),
    link_type TEXT NOT NULL,
    raw_name TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX review_entries_record ON review_entries (workspace, record_id);
