import sqlite3
import tempfile
import unittest
from pathlib import Path
from guardian.stage_account_guard import SharedAccountFairness, authorize_request
from guardian.test_durable_challenges import TestStore
from guardian.test_stage_account_guard import Verifier


class SharedIdentityBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = TestStore(str(Path(tmp.name)/"identity.sqlite"))
        self.store.pepper = b"test-only-pepper"*3
        with self.store.transaction() as db:
            db.execute("CREATE TABLE identity_budget_v2 (identity TEXT PRIMARY KEY, window_start INTEGER NOT NULL, used INTEGER NOT NULL)")
        self.now = 1800000000

    def open(self, limit=2, capacity=2):
        return SharedAccountFairness(self.store, limit=limit, capacity=capacity, clock=lambda: self.now)

    def test_workers_share_quota(self):
        subject = ("https://example.test", "user_a")
        self.assertTrue(self.open().take(subject))
        self.assertTrue(self.open().take(subject))
        self.assertFalse(self.open().take(subject))
        self.assertTrue(self.open().take(("https://example.test", "user_b")))

    def test_bound_and_expiry(self):
        a,b,c = [("https://example.test","user_"+v) for v in "abc"]
        self.assertTrue(self.open().take(a))
        self.assertTrue(self.open().take(b))
        self.assertFalse(self.open().take(c))
        self.now += 60
        self.assertTrue(self.open().take(c))

    def test_backward_clock(self):
        a = ("https://example.test", "user_a")
        self.assertTrue(self.open().take(a))
        self.now -= 1
        self.assertFalse(self.open().take(a))

    def test_digest_only(self):
        self.assertTrue(self.open().take(("https://example.test","user_a")))
        with self.store.transaction() as db:
            row = db.execute("SELECT identity FROM identity_budget_v2").fetchone()
        self.assertRegex(row[0], r"^[a-f0-9]{64}$")
        self.assertNotIn("user_a", row[0])

    def test_download_scope_separate(self):
        identity = ("https://example.test", "user_a")
        account = self.open(limit=1)
        download = SharedAccountFairness(self.store, limit=1, capacity=2, clock=lambda: self.now, scope='release-download')
        self.assertTrue(account.take(identity))
        self.assertFalse(account.take(identity))
        self.assertTrue(download.take(identity))
        self.assertFalse(download.take(identity))
        with self.assertRaises(ValueError):
            SharedAccountFairness(self.store, scope="untrusted")

    def test_storage_error_is_unavailable(self):
        class Broken:
            def take(self, identity):
                raise sqlite3.OperationalError("test")
        self.assertEqual(authorize_request({"HTTP_AUTHORIZATION":"Bearer a"}, Verifier(), Broken()),
                         ("503 Service Unavailable", {"error":"unavailable"}))
