-- Run ONLY on the dedicated void_guardian database as the schema owner.
-- The runtime role remains DML-only. Apply before enabling the feature.
BEGIN;
CREATE TABLE IF NOT EXISTS void_guardian.native_owner_session (
    slot SMALLINT PRIMARY KEY CHECK (slot = 1),
    digest BYTEA NOT NULL CHECK (octet_length(digest) = 32),
    expires_at BIGINT NOT NULL
);
REVOKE ALL ON void_guardian.native_owner_session FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON void_guardian.native_owner_session TO guardian_runtime;
COMMIT;
