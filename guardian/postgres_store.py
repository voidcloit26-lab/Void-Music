"""PostgreSQL adapter for the independent Guardian database.

The existing transaction core is reused verbatim. A transaction-scoped advisory
lock serializes the small invitation/activation workload across workers, so the
SQLite BEGIN IMMEDIATE semantics are preserved even across process restarts.
Use a dedicated database and role, never the bot or MARS database.
"""
from contextlib import contextmanager
from guardian.access_store import AccessStore
from psycopg import connect

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS void_guardian;
CREATE TABLE IF NOT EXISTS void_guardian.invitations (
    digest BYTEA PRIMARY KEY, remaining INTEGER NOT NULL CHECK(remaining > 0),
    expires_at BIGINT
);
CREATE TABLE IF NOT EXISTS void_guardian.activations (
    account_id TEXT PRIMARY KEY, device_fingerprint TEXT UNIQUE NOT NULL,
    activated_at BIGINT NOT NULL, revoked_at BIGINT
);
"""
LOCK_ID = 82941725011038

class _Transaction:
    def __init__(self, conn, initialize_schema):
        self.conn = conn
        self.initialize_schema = initialize_schema

    def execute(self, statement, params=()):
        # All statements are fixed internal SQL from AccessStore; only bound
        # values are supplied by callers. No dynamic user-controlled SQL.
        return self.conn.execute(statement.replace("?", "%s"), params)

    def executescript(self, _sqlite_schema):
        if self.initialize_schema:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self.conn.execute(statement)
            return
        # Managed runtime has DML-only grants. Never attempt schema creation.
        for table, columns in (
            ("invitations", "digest, remaining, expires_at"),
            ("activations", "account_id, device_fingerprint, activated_at, revoked_at"),
        ):
            qualified = "void_guardian." + table
            self.conn.execute("SELECT " + columns + " FROM " + qualified + " LIMIT 0")
            privileges = self.conn.execute(
                "SELECT " + ", ".join("has_table_privilege(current_user, %s, %s)" for _ in range(4)),
                tuple(v for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE") for v in (qualified, privilege)),
            ).fetchone()
            if not all(privileges):
                raise PermissionError("Guardian runtime table grants incomplete")
        if self.conn.execute(
            "SELECT has_schema_privilege(current_user, 'void_guardian', 'CREATE'), "
            "has_database_privilege(current_user, current_database(), 'CREATE')"
        ).fetchone() != (False, False):
            raise PermissionError("Guardian runtime role must not create schemas or tables")

class PostgresAccessStore(AccessStore):
    def __init__(self, database_url, pepper, *, allow_local_test=False, initialize_schema=True):
        self.initialize_schema = initialize_schema
        self.tls_options = {}
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(database_url)
        if allow_local_test:
            if settings.get("host") not in ("127.0.0.1", "localhost"):
                raise ValueError("Local test database only")
        else:
            # libpq's default ~/.postgresql/root.crt is absent on managed hosts.
            # Use the host trust store explicitly; never fall back to sslmode=require.
            if not settings.get('sslrootcert'):
                self.tls_options['sslrootcert'] = 'system'
            if settings.get("sslmode") != "verify-full":
                raise ValueError("Guardian PostgreSQL requires sslmode=verify-full")
            if not settings.get("host") or not settings.get("dbname") or not settings.get("user"):
                raise ValueError("Dedicated database connection required")
            if not initialize_schema and (settings['dbname'] != 'void_guardian' or settings['user'] != 'guardian_runtime'):
                raise ValueError("Managed Guardian requires its dedicated runtime role and database")
        super().__init__(database_url, pepper)

    @contextmanager
    def _transaction(self):
        # Connection context commits or rolls back, then closes. Explicit
        # READ COMMITTED plus transaction lock preserves the serial core.
        with connect(self.database, connect_timeout=8,
                     application_name="void-guardian", **self.tls_options) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.execute("SET LOCAL lock_timeout = '8s'")
                conn.execute("SET LOCAL statement_timeout = '10s'")
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
                conn.execute("SET LOCAL search_path TO void_guardian, pg_catalog")
                yield _Transaction(conn, self.initialize_schema)
