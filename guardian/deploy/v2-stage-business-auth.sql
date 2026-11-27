-- Separate V2 business authentication, only after business-role migration.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage' OR current_user IN
 ('guardian_v2_stage_runtime','guardian_v2_stage_business') THEN
   RAISE EXCEPTION 'wrong business authentication migration target';
 END IF;
END
$guard$;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE business_session_v2 (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), digest BYTEA NOT NULL CHECK(octet_length(digest)=32),
 issued_at BIGINT NOT NULL, expires_at BIGINT NOT NULL CHECK(expires_at=issued_at+300)
);
CREATE TABLE business_login_budget_v2 (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), window_start BIGINT NOT NULL,
 used INTEGER NOT NULL CHECK(used BETWEEN 1 AND 3)
);
REVOKE ALL ON business_session_v2,business_login_budget_v2 FROM PUBLIC,guardian_v2_stage_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON business_session_v2 TO guardian_v2_stage_business;
GRANT SELECT,INSERT,UPDATE ON business_login_budget_v2 TO guardian_v2_stage_business;
COMMIT;
