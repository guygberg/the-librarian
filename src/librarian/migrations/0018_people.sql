-- Preserve person ids so owners, speakers and history keep their relationships.
ALTER TABLE persons RENAME TO people;
ALTER TABLE people ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(aliases) AND json_type(aliases) = 'array');
ALTER TABLE people ADD COLUMN slack_id TEXT;
ALTER TABLE people ADD COLUMN email TEXT;
ALTER TABLE people ADD COLUMN role TEXT;
ALTER TABLE people ADD COLUMN department TEXT;

-- One primary Slack identity; retain any additional ids in the alias array.
UPDATE people SET slack_id = (
    SELECT substr(alias, 7) FROM aliases
    WHERE person_id = people.id AND workspace = people.workspace
      AND alias LIKE 'slack:%' ORDER BY id LIMIT 1
);
UPDATE people SET aliases = (
    SELECT json_group_array(alias) FROM (
        SELECT alias FROM aliases
        WHERE person_id = people.id AND workspace = people.workspace
          AND (people.slack_id IS NULL OR alias != 'slack:' || people.slack_id)
        ORDER BY id
    )
);
UPDATE people SET role = (
    SELECT json_extract(detail, '$.role') FROM presentation
    WHERE workspace = people.workspace AND kind = 'person' AND entity_id = people.id
);
UPDATE presentation SET detail = json_remove(detail, '$.role') WHERE kind = 'person';
CREATE INDEX people_slack_id ON people(workspace, slack_id);
DROP TABLE aliases;
