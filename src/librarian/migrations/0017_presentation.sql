-- User-authored presentation settings, separate from extracted source facts.
CREATE TABLE presentation (
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (workspace, kind, entity_id)
);
