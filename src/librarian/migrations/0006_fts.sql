-- One row per Source item, holding its latest revision. `body` is normalised text (see librarian.textsearch);
-- `original` is what snippets are cut from. Maintained by librarian.store, because the normalisation is not SQL.
-- Items stored before this migration are not indexed.
CREATE VIRTUAL TABLE source_search USING fts5(
    body,
    workspace UNINDEXED,
    source UNINDEXED,
    stable_id UNINDEXED,
    source_item_id UNINDEXED,
    original UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
