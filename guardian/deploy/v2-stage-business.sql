-- Staging only. Requires separately provisioned non-owner business login.
-- No passwords, account changes or paid issuance. Do not run on V1 or production.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage' OR
    current_user IN ('guardian_v2_stage_runtime','guardian_v2_stage_business') THEN
   RAISE EXCEPTION 'wrong business migration target';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='guardian_v2_stage_business'
   AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolbypassrls AND NOT rolreplication) THEN
   RAISE EXCEPTION 'separate business runtime required';
 END IF;
END
$guard$;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE business_settings_v2 (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 usd_cents INTEGER NOT NULL CHECK(usd_cents BETWEEN 1 AND 1000000)
);
INSERT INTO business_settings_v2 VALUES (1,500);
CREATE TABLE business_audit_v2 (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
 detail TEXT NOT NULL, created_at BIGINT NOT NULL
);
REVOKE ALL ON business_settings_v2,business_audit_v2 FROM PUBLIC,guardian_v2_stage_runtime;
GRANT USAGE ON SCHEMA guardian_v2_stage TO guardian_v2_stage_business;
GRANT SELECT(id,created_at) ON accounts_v2 TO guardian_v2_stage_business;
GRANT SELECT ON memberships_v2 TO guardian_v2_stage_business;
GRANT UPDATE(state) ON memberships_v2 TO guardian_v2_stage_business;
GRANT INSERT ON invitations_v2 TO guardian_v2_stage_business;
GRANT SELECT ON business_settings_v2 TO guardian_v2_stage_business;
GRANT UPDATE(usd_cents) ON business_settings_v2 TO guardian_v2_stage_business;
GRANT SELECT,INSERT ON business_audit_v2 TO guardian_v2_stage_business;
GRANT USAGE ON SEQUENCE business_audit_v2_id_seq TO guardian_v2_stage_business;
COMMIT;
