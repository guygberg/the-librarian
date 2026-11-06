-- The Slack workspace URL from `auth.test`, saved at Import so permalinks can be built offline.
CREATE TABLE slack_workspace (
    workspace TEXT PRIMARY KEY,
    url TEXT NOT NULL
);
