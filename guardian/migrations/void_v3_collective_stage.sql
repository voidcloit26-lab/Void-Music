-- Staging database only. Execute as schema owner after QA, never as runtime.
BEGIN;
DO $$ BEGIN
 IF current_database() <> 'void_guardian_v2_stage' THEN
  RAISE EXCEPTION 'unexpected database';
 END IF;
END $$;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE IF NOT EXISTS collective_codes_v3 (
 digest BYTEA PRIMARY KEY, kind TEXT NOT NULL, days INTEGER, expires_at BIGINT,
 claim_limit INTEGER NOT NULL CHECK(claim_limit BETWEEN 2 AND 100),
 used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count BETWEEN 0 AND claim_limit),
 cancelled_at BIGINT
);
CREATE TABLE IF NOT EXISTS collective_redemptions_v3 (
 digest BYTEA NOT NULL REFERENCES collective_codes_v3(digest),
 account TEXT NOT NULL REFERENCES accounts_v2(id),
 claimed_at BIGINT NOT NULL, previous_expiry BIGINT, new_expiry BIGINT,
 PRIMARY KEY(digest, account)
);
CREATE INDEX IF NOT EXISTS collective_redemptions_account_v3 ON collective_redemptions_v3(account);
REVOKE ALL ON collective_codes_v3, collective_redemptions_v3 FROM PUBLIC, guardian_v2_stage_runtime, guardian_v2_stage_business;
GRANT SELECT ON collective_codes_v3, collective_redemptions_v3 TO guardian_v2_stage_runtime, guardian_v2_stage_business;
GRANT UPDATE(used_count) ON collective_codes_v3 TO guardian_v2_stage_runtime;
GRANT INSERT ON collective_redemptions_v3 TO guardian_v2_stage_runtime;
GRANT INSERT ON collective_codes_v3 TO guardian_v2_stage_business;
GRANT UPDATE(cancelled_at) ON collective_codes_v3 TO guardian_v2_stage_business;
COMMIT;
