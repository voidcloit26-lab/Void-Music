-- Isolated staging only. Run as schema owner after reviewed test results.
BEGIN;
DO $$ BEGIN
 IF current_database() <> 'void_guardian_v2_stage' THEN
  RAISE EXCEPTION 'unexpected database';
 END IF;
END $$;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE IF NOT EXISTS extended_library_v4 (
 account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
 revision BIGINT NOT NULL CHECK(revision > 0),
 payload TEXT NOT NULL CHECK(octet_length(payload) <= 524288),
 updated_at BIGINT NOT NULL
);
REVOKE ALL ON extended_library_v4 FROM PUBLIC, guardian_v2_stage_runtime, guardian_v2_stage_business;
GRANT SELECT, INSERT ON extended_library_v4 TO guardian_v2_stage_runtime;
GRANT UPDATE(revision,payload,updated_at) ON extended_library_v4 TO guardian_v2_stage_runtime;
COMMIT;
