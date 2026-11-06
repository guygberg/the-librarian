-- Core memory schema. Every row carries its Workspace, even though each Workspace has its own file.

CREATE TABLE source_items (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace, source, stable_id)
);

-- Immutable: a changed source item is a new revision, never an update.
CREATE TABLE source_item_revisions (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    source_item_id INTEGER NOT NULL REFERENCES source_items(id),
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (source_item_id, revision)
);

CREATE TRIGGER source_item_revisions_no_update BEFORE UPDATE ON source_item_revisions
BEGIN SELECT RAISE(ABORT, 'source item revisions are immutable'); END;

CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE aliases (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    alias TEXT NOT NULL,
    UNIQUE (workspace, alias)
);

CREATE TABLE person_events (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    at TEXT NOT NULL
);

CREATE TRIGGER person_events_no_update BEFORE UPDATE ON person_events
BEGIN SELECT RAISE(ABORT, 'person events are append-only'); END;

CREATE TRIGGER person_events_no_delete BEFORE DELETE ON person_events
BEGIN SELECT RAISE(ABORT, 'person events are append-only'); END;

CREATE TABLE records (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('project', 'action_item', 'decision', 'blocker', 'open_question')),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    parent_id INTEGER REFERENCES records(id),
    lifecycle TEXT NOT NULL DEFAULT 'open'
        CHECK (lifecycle IN ('open', 'pending', 'suspended', 'done', 'dropped', 'superseded')),
    basis TEXT NOT NULL DEFAULT 'inferred'
        CHECK (basis IN ('stated', 'inferred', 'confirmed')),
    commitment TEXT CHECK (commitment IN ('intention', 'request', 'commitment')),
    owner_person_id INTEGER REFERENCES persons(id),
    stated_deadline TEXT,
    reasoning TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (parent_id IS NULL OR kind = 'project'),
    CHECK (commitment IS NULL OR kind = 'action_item'),
    CHECK (owner_person_id IS NULL OR kind = 'action_item'),
    CHECK (stated_deadline IS NULL OR kind = 'action_item'),
    CHECK (reasoning IS NULL OR kind = 'decision')
);

-- Ends are (type, id) pairs: 'record', 'person' or 'source_item'.
CREATE TABLE links (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'belongs_to', 'owner', 'waiting_on', 'blocks', 'supersedes',
        'related_to', 'mentions', 'evidence')),
    from_type TEXT NOT NULL CHECK (from_type IN ('record', 'person', 'source_item')),
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL CHECK (to_type IN ('record', 'person', 'source_item')),
    to_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace, type, from_type, from_id, to_type, to_id)
);
CREATE INDEX links_to ON links (workspace, to_type, to_id);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    record_id INTEGER NOT NULL REFERENCES records(id),
    revision_id INTEGER NOT NULL REFERENCES source_item_revisions(id),
    locator TEXT NOT NULL,
    quote TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('supports', 'completes', 'contradicts')),
    retrieved_at TEXT NOT NULL,
    gloss TEXT
);
CREATE INDEX evidence_record ON evidence (workspace, record_id);
