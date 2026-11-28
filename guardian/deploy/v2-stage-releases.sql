-- Reviewed additive migration only; do not apply to production or customer role.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage'
 OR current_user <> 'guardian_v2_stage_owner' THEN
   RAISE EXCEPTION 'wrong release registry migration target';
 END IF;
END
$guard$;
CREATE TABLE IF NOT EXISTS guardian_v2_stage.releases_v2 (
 sequence BIGINT PRIMARY KEY CHECK(sequence>0),
 payload BYTEA NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 4096),
 signature BYTEA NOT NULL CHECK(octet_length(signature) BETWEEN 1 AND 80),
 published_at BIGINT NOT NULL CHECK(published_at>0)
);
REVOKE ALL ON guardian_v2_stage.releases_v2 FROM PUBLIC, guardian_v2_stage_runtime;
GRANT SELECT ON guardian_v2_stage.releases_v2 TO guardian_v2_stage_runtime;
COMMIT;
