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


    def test_real_signed_session_and_cross_worker_proof(self):
        # Synthetic local RSA issuer, not a live Clerk tenant.
        import time
        import jwt
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        from guardian.clerk_session import ClerkSessionVerifier
        from guardian.account_protocol_v2 import AccountProtocol, message
        from guardian.device_protocol import b64, read_device_key
        from guardian.durable_challenges import DurableChallenges
        from guardian.access_store import AccessDenied

        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = rsa_key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        verifier = ClerkSessionVerifier(issuer=self.issuer, audience='void-music-api', public_key_pem=pem)
        now = int(time.time())
        token = jwt.encode(dict(iss=self.issuer, aud='void-music-api', sub='user_new',
            sid='sess_new', iat=now, nbf=now, exp=now+60), rsa_key, algorithm='RS256')
        key = ec.generate_private_key(ec.SECP256R1())
        pub = b64(key.public_key().public_bytes(serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo))
        fp = read_device_key(pub)[1]
        second = self.reopen()
        a = AccountProtocol(self.store, verifier, challenges=DurableChallenges(self.store))
        b = AccountProtocol(second, verifier, challenges=DurableChallenges(second))
        def prepare(action, body):
            nonce = a.challenge(token,pub,action,body)['nonce']
            sig = b64(key.sign(message(nonce,fp,'sess_new','user_new',action,body),ec.ECDSA(hashes.SHA256())))
            return nonce,sig
        def execute(action, body):
            nonce,sig = prepare(action,body)
            result = b.execute(token,pub,nonce,sig,action,body)
            with self.assertRaises(AccessDenied):
                a.execute(token,pub,nonce,sig,action,body)
            return result
        registered = execute('register',{})
        account = registered['account']
        self.assertEqual(execute('status',{})['status'],'unactivated')
        invitation = self.store.owner_issue_free(self.owner,account,'lifetime')
        execute('redeem_free',{'code':invitation})
        self.assertEqual(execute('status',{})['status'],'active')
        self.assertEqual(execute('cloud_write',{'revision':0,'library':self.data}),{'revision':1})
        self.assertEqual(execute('cloud_read',{})['library'],self.data)
        self.store.change_state(self.owner,account,'suspended')
        self.assertEqual(execute('status',{})['status'],'suspended')


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
