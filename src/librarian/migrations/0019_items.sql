-- Rename first so SQLite updates every existing foreign-key reference.
ALTER TABLE records RENAME TO items;

-- Tags use a separate membership table; items no longer carry a type discriminator.
CREATE TABLE tags (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    workspace TEXT NOT NULL
);
INSERT INTO tags SELECT id, workspace FROM items WHERE kind = 'project';

CREATE TABLE items_new (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    parent_id INTEGER REFERENCES items(id),
    lifecycle TEXT NOT NULL DEFAULT 'open'
        CHECK (lifecycle IN ('open', 'pending', 'suspended', 'done', 'dropped', 'superseded')),
    basis TEXT NOT NULL DEFAULT 'inferred' CHECK (basis IN ('stated', 'inferred', 'confirmed')),
    owner_person_id INTEGER REFERENCES people(id),
    stated_deadline TEXT,
    reasoning TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (parent_id IS NULL OR parent_id != id)
);
INSERT INTO items_new
SELECT id, workspace, title, body, parent_id, lifecycle, basis, owner_person_id,
       stated_deadline, reasoning, created_at, updated_at FROM items;
PRAGMA legacy_alter_table=ON;
DROP TABLE items;
ALTER TABLE items_new RENAME TO items;
PRAGMA legacy_alter_table=OFF;
CREATE INDEX items_parent ON items(workspace, parent_id);

-- Convert previously saved checklist state into actual child items.
CREATE TEMP TABLE checklist_migration AS
SELECT p.workspace, p.entity_id AS parent_id, CAST(c.key AS INTEGER) AS position,
       c.value AS completed,
       (SELECT COALESCE(MAX(id), 0) FROM items) + ROW_NUMBER() OVER (
           ORDER BY p.workspace, p.entity_id, CAST(c.key AS INTEGER)) AS child_id
FROM presentation p, json_each(p.detail, '$.checks') c
WHERE p.kind = 'item' AND json_type(p.detail, '$.checks') = 'array'
  AND EXISTS (SELECT 1 FROM items i WHERE i.id = p.entity_id AND i.workspace = p.workspace);
INSERT INTO items (id, workspace, title, parent_id, lifecycle, basis, created_at, updated_at)
SELECT child_id, workspace,
       CASE position WHEN 0 THEN 'Review the available context'
                     WHEN 1 THEN 'Confirm the next steps'
                     WHEN 2 THEN 'Share an update with the team'
                     ELSE 'Checklist item ' || (position + 1) END,
       parent_id, CASE WHEN completed THEN 'done' ELSE 'open' END, 'confirmed',
       strftime('%Y-%m-%dT%H:%M:%SZ','now'), strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM checklist_migration;
INSERT INTO record_events(workspace, record_id, event, detail, at)
SELECT workspace, child_id, 'create', '{}', strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM checklist_migration;
INSERT INTO record_events(workspace, record_id, event, detail, at)
SELECT workspace, child_id, 'status_change', '{"lifecycle":"done"}',
       strftime('%Y-%m-%dT%H:%M:%SZ','now')
FROM checklist_migration WHERE completed;
UPDATE presentation SET detail = json_remove(detail, '$.checks') WHERE kind = 'item';
DROP TABLE checklist_migration;

CREATE TRIGGER items_parent_insert BEFORE INSERT ON items WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'parent item must be in the same workspace')
    WHERE NOT EXISTS (SELECT 1 FROM items WHERE id = NEW.parent_id AND workspace = NEW.workspace);
END;
CREATE TRIGGER items_parent_update BEFORE UPDATE OF parent_id ON items WHEN NEW.parent_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'parent item must be in the same workspace')
    WHERE NOT EXISTS (SELECT 1 FROM items WHERE id = NEW.parent_id AND workspace = NEW.workspace);
    SELECT RAISE(ABORT, 'sub-item hierarchy cannot contain a cycle')
    WHERE NEW.id IN (
        WITH RECURSIVE ancestors(id, parent_id) AS (
            SELECT id, parent_id FROM items WHERE id = NEW.parent_id
            UNION SELECT i.id, i.parent_id FROM items i JOIN ancestors a ON i.id = a.parent_id
        ) SELECT id FROM ancestors
    );
END;
