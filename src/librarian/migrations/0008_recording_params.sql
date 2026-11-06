-- The model and language a transcript was made with; the same bytes with other parameters are transcribed again.
ALTER TABLE recording_transcripts ADD COLUMN params TEXT NOT NULL DEFAULT '';
