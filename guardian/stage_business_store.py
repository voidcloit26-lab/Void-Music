"""V2 staging business storage, deliberately separate from customer runtime.

Not mounted on a public service. A separately authenticated owner credential
must be injected; do not pass a customer Clerk verifier.
"""
from contextlib import contextmanager
import re
import time
from guardian.business_store import BusinessStore, BusinessDenied
from guardian.stage_store import Transaction
from guardian.stage_target import business_connection_options, DATABASE, BUSINESS_ROLE, SCHEMA


class StageBusinessStore(BusinessStore):
    def __init__(self, database_url, pepper, *, sandbox=False, owner_id, verify_owner, clock=time.time):
        if sandbox is not True:
            raise BusinessDenied("staging only")
        if not isinstance(pepper, bytes) or not 32 <= len(pepper) <= 64:
            raise ValueError("staging secret required")
        if not isinstance(owner_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", owner_id):
            raise ValueError("invalid owner identity")
        if not callable(verify_owner):
            raise ValueError("independent owner verifier required")
        self.options = business_connection_options(database_url)
        self.pepper, self.clock = pepper, clock
        self.owner_id, self.verify_owner = owner_id, verify_owner
        with self.transaction() as db:
            db.execute("SELECT id,created_at FROM accounts_v2 LIMIT 0")
            db.execute("SELECT account,kind,expires_at,state FROM memberships_v2 LIMIT 0")
            db.execute("SELECT singleton,usd_cents FROM business_settings_v2 LIMIT 0")
            db.execute("SELECT id,actor,action,target,detail,created_at FROM business_audit_v2 LIMIT 0")
            for column in ("device", "recovery"):
                if db.execute("SELECT has_column_privilege(current_user, ?, ?, 'SELECT')",
                              (SCHEMA + ".accounts_v2", column)).fetchone()[0]:
                    raise PermissionError("business role may not access device or recovery data")
            for table in ("external_identity_v2", "cloud_library_v2", "proof_challenges_v2", "request_budget_v2"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    if db.execute("SELECT has_table_privilege(current_user, ?, ?)",
                                  (SCHEMA + "." + table, privilege)).fetchone()[0]:
                        raise PermissionError("business role has customer-only privileges")
            for table in ("accounts_v2", "invitations_v2", "memberships_v2", "business_audit_v2"):
                if db.execute("SELECT has_table_privilege(current_user, ?, 'DELETE')",
                              (SCHEMA + "." + table,)).fetchone()[0]:
                    raise PermissionError("business role may not delete records")
            for privilege in ("UPDATE", "TRUNCATE"):
                if db.execute("SELECT has_table_privilege(current_user, ?, ?)",
                              (SCHEMA + ".business_audit_v2", privilege)).fetchone()[0]:
                    raise PermissionError("audit records must be append-only")

    @contextmanager
    def transaction(self):
        import certifi
        from psycopg import connect
        with connect(**self.options, sslrootcert=certifi.where(), connect_timeout=8,
                     application_name="void-guardian-v2-stage-business") as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.execute("SET LOCAL lock_timeout = '8s'")
                conn.execute("SET LOCAL statement_timeout = '10s'")
                if conn.execute("SELECT current_database(),current_user").fetchone() != (DATABASE, BUSINESS_ROLE):
                    raise PermissionError("unexpected staging business target")
                if conn.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolreplication FROM pg_roles WHERE rolname=current_user").fetchone() != (False,):
                    raise PermissionError("unsafe staging business role")
                if conn.execute("SELECT has_schema_privilege(current_user,%s,'CREATE'),has_database_privilege(current_user,current_database(),'CREATE')", (SCHEMA,)).fetchone() != (False, False):
                    raise PermissionError("business role cannot create objects")
                conn.execute("SET LOCAL search_path TO guardian_v2_stage, pg_catalog")
                # Same lock as customer store so issuance, redemption and suspension serialize.
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (82941725011040,))
                yield Transaction(conn)
