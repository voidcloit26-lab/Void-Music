-- Additive isolated migration. Download tickets are ephemeral and single-use.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage'
 OR current_user <> 'guardian_v2_stage_owner' THEN
   RAISE EXCEPTION 'wrong download-ticket migration target';
 END IF;
END
$guard$;
CREATE TABLE IF NOT EXISTS guardian_v2_stage.release_downloads_v2 (
 digest BYTEA PRIMARY KEY CHECK(octet_length(digest)=32),
 identity BYTEA UNIQUE NOT NULL CHECK(octet_length(identity)=32),
 session_digest BYTEA NOT NULL CHECK(octet_length(session_digest)=32),
 account TEXT NOT NULL REFERENCES guardian_v2_stage.accounts_v2(id),
 device TEXT NOT NULL CHECK(length(device)=64),
 sequence BIGINT NOT NULL CHECK(sequence>0),
 expires_at BIGINT NOT NULL CHECK(expires_at>0)
);
GRANT SELECT,INSERT,DELETE ON guardian_v2_stage.release_downloads_v2 TO guardian_v2_stage_runtime;
COMMIT;
