import concurrent.futures
import hashlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from guardian.access_store import AccessStore, AccessDenied

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(pathlib.Path(self.tmp.name) / "test.sqlite")
        self.store = AccessStore(self.path, b"x" * 32)

    def identity(self, i):
        return str(100000000000000000 + i), hashlib.sha256(str(i).encode()).hexdigest()

    def count(self):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT count(*) FROM invitations").fetchone()[0]

    def test_single_and_retry(self):
        code = self.store.generate()
        self.assertEqual(self.store.redeem(code, *self.identity(1)), "activated")
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.store.redeem(code, *self.identity(1)), "already_active")
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, *self.identity(2))
        self.assertTrue(self.store.is_active(*self.identity(1)))

    def test_collective_concurrent(self):
        code = self.store.generate(5)
        def attempt(i):
            try:
                return self.store.redeem(code, *self.identity(i)) == "activated"
            except AccessDenied:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(30)))
        self.assertEqual(sum(results), 5)
        self.assertEqual(self.count(), 0)

    def test_expiry_keeps_activations(self):
        with patch("guardian.access_store.time.time", return_value=100):
            code = self.store.generate(3, 10)
            self.store.redeem(code, *self.identity(1))
        with patch("guardian.access_store.time.time", return_value=111):
            self.assertEqual(self.store.cleanup(), 1)
            self.assertTrue(self.store.is_active(*self.identity(1)))
            with self.assertRaises(AccessDenied):
                self.store.redeem(code, *self.identity(2))

    def test_cancel(self):
        code = self.store.generate()
        self.assertTrue(self.store.cancel(code))
        self.assertEqual(self.count(), 0)
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, *self.identity(1))

    def test_revoke_and_device_binding(self):
        code = self.store.generate(4)
        account, device = self.identity(1)
        self.store.redeem(code, account, device)
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, account, self.identity(2)[1])
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, self.identity(2)[0], device)
        self.assertTrue(self.store.revoke(account))
        self.assertFalse(self.store.is_active(account, device))
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, account, device)

    def test_owner_cancel_by_identifier_and_list(self):
        code = self.store.generate(3)
        rows = self.store.list_invitations()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["remaining"], 3)
        self.assertNotIn(code, str(rows))
        self.assertTrue(self.store.cancel_id(rows[0]["id"]))
        self.assertEqual(self.store.list_invitations(), [])
        with self.assertRaises(AccessDenied):
            self.store.redeem(code, *self.identity(1))

    def test_owner_transfer_preserves_lifetime(self):
        code = self.store.generate()
        account, device = self.identity(1)
        self.store.redeem(code, account, device)
        new_device = self.identity(2)[1]
        before = self.store.list_activations()[0]["activated_at"]
        self.assertTrue(self.store.transfer(account, device, new_device))
        self.assertFalse(self.store.is_active(account, device))
        self.assertTrue(self.store.is_active(account, new_device))
        self.assertEqual(self.store.list_activations()[0]["activated_at"], before)
        self.assertFalse(self.store.transfer(account, device, self.identity(3)[1]))
        self.assertTrue(self.store.revoke(account))
        self.assertFalse(self.store.transfer(account, new_device, self.identity(3)[1]))

    def test_invalid_limit_and_hashed_storage(self):
        with self.assertRaises(ValueError):
            self.store.generate(0)
        code = self.store.generate()
        with sqlite3.connect(self.path) as db:
            digest = db.execute("SELECT digest FROM invitations").fetchone()[0]
        self.assertEqual(len(digest), 32)
        self.assertNotEqual(digest, code.encode())

if __name__ == "__main__":
    unittest.main()
