CREATE TABLE slack_picks (
    workspace TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    PRIMARY KEY (workspace, conversation_id)
);

-- A row means channels.json has already been offered once, so later edits are never overwritten by it.
CREATE TABLE slack_picks_seeded (
    workspace TEXT PRIMARY KEY
);
