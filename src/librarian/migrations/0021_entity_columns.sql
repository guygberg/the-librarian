-- One table per entity: what the UI saved in the shared presentation table becomes columns
-- on the entity it describes, and the workspace-wide setting gets its own one-row table.

ALTER TABLE items ADD COLUMN priority INTEGER CHECK (priority BETWEEN 0 AND 100);
ALTER TABLE items ADD COLUMN notes TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(notes) AND json_type(notes) = 'array');
ALTER TABLE people ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1));
ALTER TABLE tags ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1));
ALTER TABLE tags ADD COLUMN color TEXT CHECK (color IS NULL OR color GLOB '#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]');

CREATE TABLE settings (
    workspace TEXT PRIMARY KEY,
    sound INTEGER NOT NULL DEFAULT 0 CHECK (sound IN (0, 1))
);

UPDATE items SET
    priority = (
        SELECT json_extract(detail, '$.priority') FROM presentation
        WHERE workspace = items.workspace AND kind = 'item' AND entity_id = items.id
          AND json_type(detail, '$.priority') = 'integer'
          AND json_extract(detail, '$.priority') BETWEEN 0 AND 100
    ),
    notes = COALESCE((
        SELECT json_extract(detail, '$.notes') FROM presentation
        WHERE workspace = items.workspace AND kind = 'item' AND entity_id = items.id
          AND json_type(detail, '$.notes') = 'array'
    ), '[]');

UPDATE people SET favorite = 1 WHERE EXISTS (
    SELECT 1 FROM presentation
    WHERE workspace = people.workspace AND kind = 'person' AND entity_id = people.id
      AND json_extract(detail, '$.favorite') = 1
);

UPDATE tags SET
    favorite = EXISTS (
        SELECT 1 FROM presentation
        WHERE workspace = tags.workspace AND kind = 'project' AND entity_id = tags.item_id
          AND json_extract(detail, '$.favorite') = 1
    ),
    color = (
        SELECT json_extract(detail, '$.color') FROM presentation
        WHERE workspace = tags.workspace AND kind = 'project' AND entity_id = tags.item_id
          AND json_extract(detail, '$.color') GLOB '#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]'
    );

INSERT INTO settings (workspace, sound)
SELECT workspace, 1 FROM presentation
WHERE kind = 'settings' AND entity_id = 0 AND json_extract(detail, '$.sound') = 1;

DROP TABLE presentation;
