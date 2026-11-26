import os
import secrets
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.unified_sandbox import UnifiedSandboxStore, PostgresUnifiedTestStore
from guardian.business_store import BusinessDenied
from guardian.cloud_store import RevisionConflict
from guardian.membership_rules import MembershipDenied


class SharedContract:
    issuer = 'https://example.clerk.accounts.dev'
    owner = 'A' * 43

    def configure(self):
        self.now = 1800000000
        self.a, self.recovery = self.store.register(self.issuer, 'user_a', 'a'*64)
        self.b, _ = self.store.register(self.issuer, 'user_b', 'b'*64)
        self.data = {'favorites': ['song_a'], 'playlists': [], 'preferences': {'theme': 'dark'}}

    def auth(self, token):
        return ('admin' if token == self.owner else 'customer', self.now)

    def test_owner_grant_visible_to_customer_and_recovery_preserves_cloud(self):
        key = self.store.owner_issue_free(self.owner, self.a, 'lifetime')
        self.store.redeem(self.a, 'a'*64, key)
        self.assertEqual(self.store.member(self.owner, self.a)['status'], 'active')
        self.assertEqual(self.store.write_library(self.a, 'a'*64, 0, self.data), 1)
        account, _ = self.store.recover_linked(self.issuer, 'user_a', self.recovery, 'c'*64)
        self.assertEqual(account, self.a)
        reopened = self.reopen()
        self.assertEqual(reopened.read_library(self.a, 'c'*64), (1, self.data))
        self.assertEqual(reopened.resolve(self.issuer, 'user_a', 'c'*64), self.a)
        with self.assertRaises(MembershipDenied):
            reopened.read_library(self.a, 'a'*64)
        self.assertNotIn(key, str(reopened.audit(self.owner)))

    def test_suspension_immediately_blocks_new_cloud_writes(self):
        self.store.redeem(self.a, 'a'*64, self.store.owner_issue_free(self.owner, self.a, 'trial', days=1))
        self.store.write_library(self.a, 'a'*64, 0, self.data)
        self.store.change_state(self.owner, self.a, 'suspended')
        with self.assertRaises(MembershipDenied):
            self.store.write_library(self.a, 'a'*64, 1, self.data)
        self.assertEqual(self.store.read_library(self.a, 'a'*64), (1, self.data))
        self.store.change_state(self.owner, self.a, 'enabled')
        self.assertEqual(self.store.write_library(self.a, 'a'*64, 1, self.data), 2)

    def test_isolation_and_concurrent_revision(self):
        with self.assertRaises(BusinessDenied):
            self.store.owner_issue_free('B'*43, self.a, 'lifetime')
        self.store.redeem(self.a, 'a'*64, self.store.owner_issue_free(self.owner, self.a, 'lifetime'))
        def write(_):
            try:
                self.store.write_library(self.a, 'a'*64, 0, self.data)
                return True
            except RevisionConflict:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(write, range(6))), 1)
        self.assertEqual(self.store.read_library(self.b, 'b'*64), (0, None))
        with self.assertRaises(MembershipDenied):
            self.store.read_library(self.a, 'b'*64)


class SQLiteUnifiedTests(SharedContract, unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name)/'qa.sqlite')
        self.store = self.reopen()
        self.configure()

    def reopen(self):
        return UnifiedSandboxStore(self.path, b'x'*32, sandbox=True, issuer=self.issuer,
            owner_id='admin', verify_owner=self.auth, clock=lambda: self.now)


@unittest.skipUnless(os.getenv('VOID_GUARDIAN_V2_LOCAL_TEST_URL'), 'local PostgreSQL not provisioned')
class PostgresUnifiedTests(SharedContract, unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.schema = 'void_v2_test_' + secrets.token_hex(16)
        self.store = self.reopen()
        self.addCleanup(self.cleanup)
        self.configure()

    def reopen(self):
        return PostgresUnifiedTestStore(os.environ['VOID_GUARDIAN_V2_LOCAL_TEST_URL'], b'x'*32,
            schema=self.schema, sandbox=True, issuer=self.issuer, owner_id='admin',
            verify_owner=self.auth, clock=lambda: self.now)

    def cleanup(self):
        from psycopg import sql
        with self.store._connection() as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
