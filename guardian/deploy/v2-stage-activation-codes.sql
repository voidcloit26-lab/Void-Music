-- Additive migration, isolated Guardian V2 staging only. Existing codes remain intact.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage' OR current_user IN
 ('guardian_v2_stage_runtime','guardian_v2_stage_business') THEN
 RAISE EXCEPTION 'wrong activation migration target';
 END IF;
END
$guard$;
SET LOCAL search_path TO guardian_v2_stage, pg_catalog;
CREATE TABLE activation_codes_v2 (
 digest BYTEA PRIMARY KEY CHECK(octet_length(digest)=32),
 kind TEXT NOT NULL CHECK(kind IN ('annual','renewal','lifetime','trial','complimentary')),
 days INTEGER, expires_at BIGINT, bound_identity BYTEA,
 redeemed_account TEXT REFERENCES accounts_v2(id), redeemed_at BIGINT, cancelled_at BIGINT,
 CHECK((redeemed_account IS NULL)=(redeemed_at IS NULL)),
 CHECK(cancelled_at IS NULL OR redeemed_at IS NULL),
 CHECK(bound_identity IS NULL OR octet_length(bound_identity)=32),
 CHECK((kind IN ('trial','complimentary') AND days IS NOT NULL AND days BETWEEN 1 AND 365) OR
       (kind NOT IN ('trial','complimentary') AND days IS NULL))
);
REVOKE ALL ON activation_codes_v2 FROM PUBLIC;
GRANT SELECT ON activation_codes_v2 TO guardian_v2_stage_runtime;
GRANT UPDATE(redeemed_account,redeemed_at) ON activation_codes_v2 TO guardian_v2_stage_runtime;
GRANT SELECT,INSERT ON activation_codes_v2 TO guardian_v2_stage_business;
GRANT UPDATE(cancelled_at) ON activation_codes_v2 TO guardian_v2_stage_business;
COMMIT;
