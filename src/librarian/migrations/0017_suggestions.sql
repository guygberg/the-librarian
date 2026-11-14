-- Standalone Suggestions: stored, source-linked, confidence-graded proposals that only the person's Accept turns
-- into Records, Persons or Links. Analysis never writes those, and is tracked apart from extraction.

-- A Tag replaces a Project: one concept, so every Project row becomes a Tag and the word leaves the schema.
-- SQLite cannot alter a CHECK, so records is rebuilt; every other column and constraint is unchanged. Child rows
-- point at records by name, so they follow the rebuild.
CREATE TABLE records_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('tag', 'action_item', 'decision', 'blocker', 'open_question')),
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
    CHECK (parent_id IS NULL OR kind = 'tag'),
    CHECK (commitment IS NULL OR kind = 'action_item'),
    CHECK (owner_person_id IS NULL OR kind = 'action_item'),
    CHECK (stated_deadline IS NULL OR kind = 'action_item'),
    CHECK (reasoning IS NULL OR kind = 'decision')
);
INSERT INTO records_new
    SELECT id, workspace, CASE kind WHEN 'project' THEN 'tag' ELSE kind END, title, body, parent_id,
           lifecycle, basis, commitment, owner_person_id, stated_deadline, reasoning, created_at, updated_at
    FROM records;
-- This trigger reads records, so SQLite refuses the rename while it exists.
DROP TRIGGER record_events_no_delete;
DROP TABLE records;
ALTER TABLE records_new RENAME TO records;
CREATE TRIGGER record_events_no_delete BEFORE DELETE ON record_events
WHEN OLD.record_id IS NULL OR EXISTS (SELECT 1 FROM records WHERE id = OLD.record_id)
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;

CREATE TABLE review_entries_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'unconfirmed_person', 'unknown_speaker', 'inferred_tag', 'suggested_tag', 'merge_tag')),
    record_id INTEGER NOT NULL REFERENCES records(id),
    link_type TEXT NOT NULL,
    raw_name TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    other_record_id INTEGER REFERENCES records(id),
    resolution TEXT CHECK (resolution IN ('accepted', 'rejected'))
);
INSERT INTO review_entries_new
    SELECT id, workspace, REPLACE(kind, '_project', '_tag'), record_id, link_type, raw_name, created_at,
           resolved_at, other_record_id, resolution
    FROM review_entries;
DROP TABLE review_entries;
ALTER TABLE review_entries_new RENAME TO review_entries;
CREATE INDEX review_entries_record ON review_entries (workspace, record_id);

ALTER TABLE project_aliases RENAME TO tag_aliases;

-- The logged move of a Record under a Project is now a move under a Tag.
-- The trigger blocking updates is dropped and restored around the rewrite.
DROP TRIGGER record_events_no_update;
UPDATE record_events
    SET event = 'tag_move', detail = json_set(json_remove(detail, '$.project_id'), '$.tag_id',
                                              json_extract(detail, '$.project_id'))
    WHERE event = 'project_move';
CREATE TRIGGER record_events_no_update BEFORE UPDATE ON record_events
BEGIN SELECT RAISE(ABORT, 'record events are append-only'); END;

-- Model runs record why they were made, so a Suggestions run is never counted or read as an extraction run.
ALTER TABLE extraction_runs ADD COLUMN purpose TEXT NOT NULL DEFAULT 'extraction'
    CHECK (purpose IN ('extraction', 'suggestions'));

CREATE TABLE suggestions (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('new_tag', 'new_item', 'link')),
    link_type TEXT CHECK (link_type IN (
        'belongs_to', 'owner', 'waiting_on', 'blocks', 'supersedes',
        'related_to', 'mentions', 'contradicts')),
    payload TEXT NOT NULL,
    from_type TEXT CHECK (from_type IN ('record', 'person', 'source_item')),
    from_id INTEGER,
    to_type TEXT CHECK (to_type IN ('record', 'person', 'source_item')),
    to_id INTEGER,
    run_id INTEGER NOT NULL REFERENCES extraction_runs(id),
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    band TEXT NOT NULL CHECK (band IN ('high', 'medium', 'low')),
    basis TEXT NOT NULL CHECK (basis IN ('stated', 'inferred')),
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'superseded')),
    dedupe_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE (workspace, dedupe_key),
    CHECK ((kind = 'link') = (link_type IS NOT NULL)),
    CHECK ((from_type IS NULL) = (from_id IS NULL)),
    CHECK ((to_type IS NULL) = (to_id IS NULL)),
    CHECK ((status = 'pending') = (resolved_at IS NULL)),
    CHECK (basis = 'stated' OR confidence <= 89)
);
CREATE INDEX suggestions_status ON suggestions (workspace, status, confidence);

CREATE TABLE suggestion_evidence (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
    revision_id INTEGER NOT NULL REFERENCES source_item_revisions(id),
    locator TEXT NOT NULL,
    quote TEXT NOT NULL
);
CREATE INDEX suggestion_evidence_suggestion ON suggestion_evidence (workspace, suggestion_id);
CREATE INDEX suggestion_evidence_revision ON suggestion_evidence (workspace, revision_id);

CREATE TABLE suggestion_events (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
    event TEXT NOT NULL CHECK (event IN ('created', 'accepted', 'rejected', 'superseded', 'edited')),
    detail TEXT NOT NULL DEFAULT '{}',
    at TEXT NOT NULL
);
CREATE INDEX suggestion_events_suggestion ON suggestion_events (workspace, suggestion_id);

CREATE TRIGGER suggestion_events_no_update BEFORE UPDATE ON suggestion_events
BEGIN SELECT RAISE(ABORT, 'suggestion events are append-only'); END;

CREATE TRIGGER suggestion_events_no_delete BEFORE DELETE ON suggestion_events
BEGIN SELECT RAISE(ABORT, 'suggestion events are append-only'); END;

-- Whether a unit has been analysed for Suggestions. Independent of extracted_units: extraction completing
-- neither implies nor suppresses it. Only a succeeded row with matching hashes skips another call.
CREATE TABLE suggestion_units (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    unit_key TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    schema_hash TEXT NOT NULL,
    run_id INTEGER REFERENCES extraction_runs(id),
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    suggestion_count INTEGER NOT NULL DEFAULT 0 CHECK (suggestion_count >= 0),
    analysed_at TEXT NOT NULL,
    UNIQUE (workspace, unit_key)
);
