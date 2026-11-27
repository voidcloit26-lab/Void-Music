"""Managed V2 staging customer storage. No schema creation or owner API."""
from contextlib import contextmanager
import time
from guardian.external_identity_store import ExternalIdentityStore
from guardian.cloud_store import CloudStore
from guardian.stage_target import connection_options, DATABASE, ROLE, SCHEMA


class Transaction:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, statement, params=()):
        return self.conn.execute(statement.replace('?', '%s'), params)


class StageStore(ExternalIdentityStore, CloudStore):
    def __init__(self, database_url, pepper, *, issuer, clock=time.time):
        if not isinstance(pepper, bytes) or not 32 <= len(pepper) <= 64:
            raise ValueError('staging server secret required')
        self.options = connection_options(database_url)
        self.pepper, self.issuer, self.clock = pepper, issuer, clock
        with self.transaction() as db:
            tables = {
                'accounts_v2': 'id,device,recovery,created_at',
                'memberships_v2': 'account,kind,expires_at,state',
                'invitations_v2': 'digest,account,kind,days,expires_at,redeemed_at',
                'external_identity_v2': 'identity,account',
                'cloud_library_v2': 'account,revision,payload,updated_at',
                'proof_challenges_v2': 'nonce,scope,device,digest,expires_at',
                'request_budget_v2': 'bucket,window_start,used',
            }
            for table, columns in tables.items():
                db.execute('SELECT ' + columns + ' FROM ' + table + ' LIMIT 0')
                privileges = ('SELECT','INSERT','DELETE') if table == 'proof_challenges_v2' else (
                    ('SELECT','INSERT') if table == 'external_identity_v2' else ('SELECT','INSERT','UPDATE'))
                for privilege in privileges:
                    if not db.execute('SELECT has_table_privilege(current_user, ?, ?)',
                                      (SCHEMA + '.' + table, privilege)).fetchone()[0]:
                        raise PermissionError('staging table grants incomplete')

    @contextmanager
    def transaction(self):
        import certifi
        from psycopg import connect
        with connect(**self.options, sslrootcert=certifi.where(), connect_timeout=8,
                     application_name='void-guardian-v2-stage') as conn:
            with conn.transaction():
                conn.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                conn.execute("SET LOCAL lock_timeout = '8s'")
                conn.execute("SET LOCAL statement_timeout = '10s'")
                if conn.execute('SELECT current_database(),current_user').fetchone() != (DATABASE,ROLE):
                    raise PermissionError('unexpected staging database')
                if conn.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() != (False,):
                    raise PermissionError('unsafe runtime role')
                if conn.execute("SELECT has_schema_privilege(current_user, %s, 'CREATE'), has_database_privilege(current_user,current_database(),'CREATE')",(SCHEMA,)).fetchone() != (False,False):
                    raise PermissionError('runtime must not create schema objects')
                conn.execute('SET LOCAL search_path TO guardian_v2_stage, pg_catalog')
                conn.execute('SELECT pg_advisory_xact_lock(%s)', (82941725011040,))
                yield Transaction(conn)
