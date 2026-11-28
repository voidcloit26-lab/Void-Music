"""Additive, opt-in collective activation schema. No runtime DDL in staging."""
DDL = """
CREATE TABLE IF NOT EXISTS collective_codes_v3 (
 digest BYTEA PRIMARY KEY, kind TEXT NOT NULL, days INTEGER, expires_at BIGINT,
 claim_limit INTEGER NOT NULL CHECK(claim_limit BETWEEN 2 AND 100),
 used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count BETWEEN 0 AND claim_limit),
 cancelled_at BIGINT
);
"""
REDEMPTIONS_DDL = """
CREATE TABLE IF NOT EXISTS collective_redemptions_v3 (
 digest BYTEA NOT NULL REFERENCES collective_codes_v3(digest),
 account TEXT NOT NULL REFERENCES accounts_v2(id),
 claimed_at BIGINT NOT NULL, previous_expiry BIGINT, new_expiry BIGINT,
 PRIMARY KEY(digest, account)
);
"""
INDEX_DDL = "CREATE INDEX IF NOT EXISTS collective_redemptions_account_v3 ON collective_redemptions_v3(account)"
def verify_stage(store, *, business=False):
    """Fail closed if the feature's migration or restricted grants are missing."""
    schema = "guardian_v2_stage."
    with store.transaction() as db:
        db.execute("SELECT digest,kind,days,expires_at,claim_limit,used_count,cancelled_at FROM collective_codes_v3 LIMIT 0")
        db.execute("SELECT digest,account,claimed_at,previous_expiry,new_expiry FROM collective_redemptions_v3 LIMIT 0")
        for table in ("collective_codes_v3", "collective_redemptions_v3"):
            for privilege in ("DELETE", "TRUNCATE"):
                if db.execute("SELECT has_table_privilege(current_user,?,?)",(schema+table,privilege)).fetchone()[0]:
                    raise PermissionError("collective history must be retained")
        for column in ("digest","kind","days","expires_at","claim_limit","used_count","cancelled_at"):
            expected = column == ("cancelled_at" if business else "used_count")
            actual = db.execute("SELECT has_column_privilege(current_user,?,?,'UPDATE')",
                                (schema+"collective_codes_v3",column)).fetchone()[0]
            if actual != expected:
                raise PermissionError("invalid collective code update grants")
        for privilege in ("INSERT", "UPDATE"):
            actual = db.execute("SELECT has_table_privilege(current_user,?,?)",
                                (schema+"collective_redemptions_v3",privilege)).fetchone()[0]
            if actual != (privilege == "INSERT" and not business):
                raise PermissionError("invalid collective redemption grants")
        if db.execute("SELECT has_table_privilege(current_user,?,'INSERT')",
                      (schema+"collective_codes_v3",)).fetchone()[0] != business:
            raise PermissionError("invalid collective issuance grants")
