-- Where a Source item came from (Slack: conversation name and kind) and whether it vanished at the source.
ALTER TABLE source_items ADD COLUMN origin_name TEXT NOT NULL DEFAULT '';
ALTER TABLE source_items ADD COLUMN origin_kind TEXT NOT NULL DEFAULT '';
ALTER TABLE source_items ADD COLUMN gone INTEGER NOT NULL DEFAULT 0 CHECK (gone IN (0, 1));
