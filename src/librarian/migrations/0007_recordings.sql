-- A recording found on disk and the hash of its bytes, recorded once it is fully local.
CREATE TABLE recording_files (
    workspace TEXT NOT NULL,
    path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    PRIMARY KEY (workspace, path)
);

-- A file hash whose transcript is stored: the Transcriber is never called for it again, whatever the path.
CREATE TABLE recording_transcripts (
    workspace TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    PRIMARY KEY (workspace, file_hash)
);
