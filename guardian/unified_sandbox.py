"""Shared customer and owner storage for isolated Guardian V2 QA only.

The same account, membership, cloud revision and audit state are visible to both
adapters. No live services, migrations, or real payment acceptance.
"""
import re
from urllib.parse import urlsplit
from guardian.business_store import BusinessStore, DDL as BUSINESS_DDL
from guardian.external_identity_store import ExternalIdentityStore, DDL as IDENTITY_DDL
from guardian.cloud_store import CloudStore, DDL as CLOUD_DDL
from guardian.postgres_identity_test_store import PostgresIdentityTestStore
from guardian.durable_challenges import DDL as CHALLENGE_DDL
from guardian.shared_budget import DDL as BUDGET_DDL


class UnifiedSandboxStore(BusinessStore, ExternalIdentityStore, CloudStore):
    """Cooperative constructors create all tables in one disposable SQLite DB."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self.transaction() as db:
            db.execute(CHALLENGE_DDL)
            db.execute(BUDGET_DDL)


class PostgresUnifiedTestStore(PostgresIdentityTestStore, BusinessStore,
                               ExternalIdentityStore, CloudStore):
    """Extends the guarded loopback-only test adapter; never accepts a live DB."""
    def __init__(self, database_url, pepper, *, schema, issuer, owner_id,
                 verify_owner, sandbox=False, **kwargs):
        if sandbox is not True:
            raise PermissionError('sandbox only')
        url = urlsplit(issuer)
        if (not isinstance(issuer, str) or len(issuer) > 256 or url.scheme != 'https'
                or not url.hostname or url.username or url.password or url.port
                or url.path or url.query or url.fragment):
            raise ValueError('exact HTTPS issuer required')
        if not isinstance(owner_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', owner_id):
            raise ValueError('invalid owner')
        if not callable(verify_owner):
            raise ValueError('owner verifier required')
        self.issuer, self.owner_id, self.verify_owner = issuer, owner_id, verify_owner
        super().__init__(database_url, pepper, schema=schema, sandbox=True, **kwargs)
        # All SQL is fixed, with no caller-supplied identifiers or values.
        business = BUSINESS_DDL.replace('id INTEGER PRIMARY KEY,',
            'id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,').replace('created_at INTEGER', 'created_at BIGINT')
        cloud = CLOUD_DDL.replace('revision INTEGER', 'revision BIGINT').replace('updated_at INTEGER', 'updated_at BIGINT')
        with self.transaction() as db:
            for statement in (IDENTITY_DDL.replace(' BLOB', ' BYTEA') + '\n' + cloud + '\n' + business + '\n' + CHALLENGE_DDL + '\n' + BUDGET_DDL).split(';'):
                if statement.strip():
                    db.execute(statement)
