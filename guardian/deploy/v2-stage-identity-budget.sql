-- Additive migration for the isolated V2 stage only.
BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'void_guardian_v2_stage'
 OR current_user <> 'guardian_v2_stage_owner' THEN
   RAISE EXCEPTION 'wrong identity-budget migration target';
 END IF;
END
$guard$;
CREATE TABLE IF NOT EXISTS guardian_v2_stage.identity_budget_v2 (
 identity TEXT PRIMARY KEY CHECK(length(identity)=64),
 window_start BIGINT NOT NULL CHECK(window_start>0),
 used INTEGER NOT NULL CHECK(used BETWEEN 1 AND 120)
);
GRANT SELECT,INSERT,UPDATE,DELETE ON guardian_v2_stage.identity_budget_v2 TO guardian_v2_stage_runtime;
COMMIT;
