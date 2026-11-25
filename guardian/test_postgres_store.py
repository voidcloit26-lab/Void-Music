"""Integration regression tests against an isolated CI-only PostgreSQL database."""
import os
import concurrent.futures
import unittest
from guardian.access_store import AccessDenied

@unittest.skipUnless(os.environ.get("VOID_GUARDIAN_POSTGRES_TEST_URL"), "PostgreSQL integration environment not supplied")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        from psycopg import connect
        from guardian.postgres_store import PostgresAccessStore
        self.Store = PostgresAccessStore
        self.url = os.environ["VOID_GUARDIAN_POSTGRES_TEST_URL"]
        from psycopg.conninfo import conninfo_to_dict
        config = conninfo_to_dict(self.url)
        if config.get("host") not in ("127.0.0.1", "localhost") or config.get("dbname") != "void_guardian_test":
            raise ValueError("Only the disposable CI database may be used")
        with connect(self.url) as conn:
            conn.execute("DROP SCHEMA IF EXISTS void_guardian CASCADE")
        self.store = PostgresAccessStore(self.url, b"p"*32, allow_local_test=True)

    def test_concurrent_redemption(self):
        code = self.store.generate(uses=3)
        def use(n):
            try:
                return self.store.redeem(code, str(10**19+n), format(n,"064x"))
            except AccessDenied:
                return "denied"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(use, range(1,9)))
        self.assertEqual(results.count("activated"),3)
        self.assertEqual(results.count("denied"),5)
        self.assertEqual(len(self.store.list_activations()),3)
        self.assertEqual(self.store.list_invitations(),[])

    def test_persistent_and_revocable(self):
        account, fp = str(10**19+1), "a"*64
        code = self.store.generate()
        self.assertEqual(self.store.redeem(code, account, fp),"activated")
        reopened = self.Store(self.url,b"p"*32,allow_local_test=True)
        self.assertEqual(reopened.redeem(code, account, fp),"already_active")
        self.assertTrue(reopened.is_active(account,fp))
        self.assertTrue(reopened.revoke(account))
        self.assertFalse(self.store.is_active(account,fp))

    def test_invalid_code_and_rollback(self):
        account, fp = str(10**19+2), "b"*64
        with self.assertRaises(AccessDenied):
            self.store.redeem("VOID-AAAAAAAA-AAAAAAAA-AAAAAAAA-AAAAAAAA",account,fp)
        self.assertEqual(self.store.list_activations(),[])
        code = self.store.generate(uses=2)
        ident = self.store.list_invitations()[0]["id"]
        self.assertTrue(self.store.cancel_id(ident))
        self.assertEqual(self.store.list_invitations(),[])

    def test_requires_verified_tls_for_real_host(self):
        with self.assertRaises(ValueError):
            self.Store(self.url,b"p"*32)
