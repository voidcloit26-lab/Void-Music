"""Disposable PostgreSQL integration adapter for Guardian V2.

Never accepts a live Guardian database, remote host, or production role.
Requires an explicitly provisioned local test database. Synthetic payments only.
"""
from contextlib import contextmanager
import re
import time
from guardian.sandbox_ledger import SandboxLedger

DB = "void_guardian_v2_test"
SCHEMA_PATTERN = re.compile(r"void_v2_test_[0-9a-f]{32}")
LOCK = 82941725011039

DDL = """
CREATE TABLE IF NOT EXISTS accounts_v2 (
    id TEXT PRIMARY KEY, device TEXT UNIQUE NOT NULL,
    recovery BYTEA UNIQUE NOT NULL, created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships_v2 (
    account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
    kind TEXT NOT NULL CHECK(kind IN ('annual','lifetime','trial','complimentary')),
    expires_at BIGINT,
    state TEXT NOT NULL CHECK(state IN ('enabled','suspended','revoked')),
    CHECK((kind='lifetime' AND expires_at IS NULL) OR
          (kind<>'lifetime' AND expires_at IS NOT NULL AND expires_at>0))
);
CREATE TABLE IF NOT EXISTS invitations_v2 (
    digest BYTEA PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts_v2(id),
    kind TEXT NOT NULL CHECK(kind IN ('lifetime','trial','complimentary')),
    days INTEGER, expires_at BIGINT NOT NULL, redeemed_at BIGINT
);
CREATE TABLE IF NOT EXISTS test_payments_v2 (
    id TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts_v2(id),
    reference TEXT NOT NULL UNIQUE, usd_cents INTEGER NOT NULL CHECK(usd_cents>0),
    recorded_at BIGINT NOT NULL, voided_at BIGINT, consumed_at BIGINT,
    CHECK(voided_at IS NULL OR consumed_at IS NULL)
);
CREATE TABLE IF NOT EXISTS test_paid_keys_v2 (
    payment TEXT PRIMARY KEY REFERENCES test_payments_v2(id),
    digest BYTEA NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('annual','renewal')),
    expires_at BIGINT NOT NULL
);
"""

def check_target(settings, schema, sandbox):
    if sandbox is not True:
        raise PermissionError("explicit sandbox required")
    if not isinstance(schema, str) or not SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("disposable test schema required")
    if set(settings) - {"host", "port", "dbname", "user", "password", "sslmode"}:
        raise ValueError("unsupported database connection options")
    if settings.get("host") != "127.0.0.1":
        raise PermissionError("local PostgreSQL only")
    if settings.get("dbname") != DB or settings.get("user") != DB:
        raise PermissionError("dedicated test database and role required")
    if settings.get("sslmode", "disable") != "disable":
        raise ValueError("local disposable database only")
    port = settings.get("port", "5432")
    if not isinstance(port, str) or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("invalid port")

class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, statement, params=()):
        # Only fixed SQL from the inherited storage methods; values stay bound.
        return self.conn.execute(statement.replace("?", "%s"), params)

class PostgresIdentityTestStore(SandboxLedger):
    def __init__(self, database_url, pepper, *, schema, sandbox=False,
                 clock=time.time, price_cents=500):
        if sandbox is not True:
            raise PermissionError("explicit sandbox required")
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(database_url)
        check_target(settings, schema, sandbox)
        if not isinstance(pepper, bytes) or len(pepper)<32:
            raise ValueError("server secret required")
        if type(price_cents) is not int or not 1<=price_cents<=1000000:
            raise ValueError("invalid USD price")
        self.settings = settings
        self.schema, self.pepper, self.clock = schema, pepper, clock
        self.price_cents = price_cents
        # Bypass SQLite-specific constructors deliberately.
        with self._connection() as conn:
            from psycopg import sql
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
            for statement in DDL.split(";"):
                if statement.strip():
                    conn.execute(statement)

    @contextmanager
    def _connection(self):
        from psycopg import connect
        # Explicit hostaddr also prevents a libpq environment override redirecting the host.
        with connect(host="127.0.0.1", hostaddr="127.0.0.1",
                     port=self.settings.get("port","5432"), dbname=DB, user=DB,
                     password=self.settings.get("password",""), sslmode="disable",
                     connect_timeout=5, application_name="void-guardian-v2-test") as conn:
            with conn.transaction():
                if conn.execute("SELECT current_database(),current_user").fetchone() != (DB,DB):
                    raise PermissionError("unexpected connected database")
                if conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone() != (False,):
                    raise PermissionError("test role cannot be superuser")
                conn.execute("SET LOCAL lock_timeout = '8s'")
                conn.execute("SET LOCAL statement_timeout = '10s'")
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
                yield conn

    @contextmanager
    def transaction(self):
        from psycopg import sql
        with self._connection() as conn:
            conn.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(self.schema)))
            yield _Transaction(conn)
