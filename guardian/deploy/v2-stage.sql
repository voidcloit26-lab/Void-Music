-- Explicit staging migration only. Run as the dedicated staging database owner.
-- Provision the non-owner runtime role separately. No credential literals here.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage' OR current_user = 'guardian_v2_stage_runtime' THEN
   RAISE EXCEPTION 'wrong migration target';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='guardian_v2_stage_runtime'
                 AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolbypassrls) THEN
   RAISE EXCEPTION 'dedicated least-privilege role required';
 END IF;
END
$guard$;
CREATE SCHEMA guardian_v2_stage;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE accounts_v2 (
 id TEXT PRIMARY KEY, device TEXT UNIQUE NOT NULL,
 recovery BYTEA UNIQUE NOT NULL, created_at BIGINT NOT NULL
);
CREATE TABLE memberships_v2 (
 account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
 kind TEXT NOT NULL CHECK(kind IN ('annual','lifetime','trial','complimentary')),
 expires_at BIGINT,
 state TEXT NOT NULL CHECK(state IN ('enabled','suspended','revoked')),
 CHECK((kind='lifetime' AND expires_at IS NULL) OR (kind<>'lifetime' AND expires_at>0 AND expires_at IS NOT NULL))
);
CREATE TABLE invitations_v2 (
 digest BYTEA PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts_v2(id),
 kind TEXT NOT NULL CHECK(kind IN ('lifetime','trial','complimentary')),
 days INTEGER, expires_at BIGINT NOT NULL, redeemed_at BIGINT
);
CREATE TABLE external_identity_v2 (
 identity BYTEA PRIMARY KEY, account TEXT UNIQUE NOT NULL REFERENCES accounts_v2(id)
);
CREATE TABLE cloud_library_v2 (
 account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
 revision BIGINT NOT NULL CHECK(revision>0), payload TEXT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE TABLE proof_challenges_v2 (
 nonce TEXT PRIMARY KEY, scope TEXT NOT NULL, device TEXT NOT NULL,
 digest TEXT NOT NULL, expires_at BIGINT NOT NULL, UNIQUE(scope, device)
);
CREATE TABLE request_budget_v2 (
 bucket TEXT PRIMARY KEY, window_start BIGINT NOT NULL, used INTEGER NOT NULL CHECK(used>0)
);
REVOKE ALL ON SCHEMA guardian_v2_stage FROM PUBLIC;
GRANT USAGE ON SCHEMA guardian_v2_stage TO guardian_v2_stage_runtime;
GRANT SELECT, INSERT, UPDATE ON accounts_v2,memberships_v2,invitations_v2,cloud_library_v2,request_budget_v2 TO guardian_v2_stage_runtime;
GRANT SELECT, INSERT ON external_identity_v2 TO guardian_v2_stage_runtime;
GRANT SELECT, INSERT, DELETE ON proof_challenges_v2 TO guardian_v2_stage_runtime;
COMMIT;
