-- How a Review entry was settled. A rejected one is remembered so the next Import does not suggest it again.
ALTER TABLE review_entries ADD COLUMN resolution TEXT CHECK (resolution IN ('accepted', 'rejected'));
