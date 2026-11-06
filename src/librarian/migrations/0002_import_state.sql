CREATE TABLE import_runs (
    id INTEGER PRIMARY KEY,
    workspace TEXT NOT NULL,
    pid INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'finished', 'interrupted'))
);

CREATE TABLE import_items (
    workspace TEXT NOT NULL,
    source TEXT NOT NULL,
    item TEXT NOT NULL,
    PRIMARY KEY (workspace, source, item)
);

-- One row per (item, stage) that has been attempted; a stage with status 'done' is never redone.
CREATE TABLE import_item_stages (
    workspace TEXT NOT NULL,
    source TEXT NOT NULL,
    item TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    error TEXT,
    run_id INTEGER NOT NULL REFERENCES import_runs(id),
    PRIMARY KEY (workspace, source, item, stage),
    FOREIGN KEY (workspace, source, item) REFERENCES import_items(workspace, source, item)
);

CREATE TABLE import_counters (
    workspace TEXT NOT NULL,
    run_id INTEGER NOT NULL REFERENCES import_runs(id),
    source TEXT NOT NULL,
    counter TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (run_id, source, counter)
);
