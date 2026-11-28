import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from guardian.cloud_store import CloudStore, RevisionConflict
from guardian.extended_library_v4 import DDL, EMPTY, ExtendedLibraryStore, normalize_extended
from guardian.membership_rules import MembershipDenied

class ExtendedLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.now = 1800000000
        self.identity = CloudStore(str(Path(temporary.name) / "library.sqlite"), b"x"*32,
                                   clock=lambda: self.now)
        with self.identity.transaction() as db:
            db.execute(DDL)
        self.store = ExtendedLibraryStore(self.identity)
        self.a, self.recovery = self.identity.create_account("a"*64)
        self.b, _ = self.identity.create_account("b"*64)
        self.identity.redeem(self.a, "a"*64, self.identity.issue_free(self.a, "trial", days=1))
        self.data = {"albums": ["MPREb"+"a"*16], "artists": ["UC"+"b"*22],
                     "history": [{"song_id": "c"*11, "timestamp_ms": 1000, "played_ms": 200}]}

    def test_revision_and_legacy_separation(self):
        self.assertEqual(self.store.read(self.a, "a"*64), (0, None))
        self.assertEqual(self.store.write(self.a, "a"*64, 0, self.data), 1)
        self.assertEqual(self.store.read(self.a, "a"*64), (1, self.data))
        self.assertEqual(self.identity.read_library(self.a, "a"*64), (0, None))
        self.assertEqual(self.store.write(self.a, "a"*64, 1, self.data), 1)
        with self.assertRaises(RevisionConflict):
            self.store.write(self.a, "a"*64, 0, self.data)

    def test_isolation_and_device_recovery(self):
        self.store.write(self.a, "a"*64, 0, self.data)
        self.assertEqual(self.store.read(self.b, "b"*64), (0, None))
        with self.assertRaises(MembershipDenied):
            self.store.read(self.a, "b"*64)
        with self.assertRaises(MembershipDenied):
            self.store.clear(self.a, "b"*64, 1)
        self.identity.recover(self.a, self.recovery, "c"*64)
        self.assertEqual(self.store.read(self.a, "c"*64), (1, self.data))
        with self.assertRaises(MembershipDenied):
            self.store.read(self.a, "a"*64)

    def test_expiry_read_and_clear_but_not_write(self):
        self.store.write(self.a, "a"*64, 0, self.data)
        self.now += 86400
        self.assertEqual(self.store.read(self.a, "a"*64), (1, self.data))
        with self.assertRaises(MembershipDenied):
            self.store.write(self.a, "a"*64, 1, EMPTY)
        self.assertEqual(self.store.clear(self.a, "a"*64, 1), 2)
        self.assertEqual(self.store.read(self.a, "a"*64), (2, EMPTY))
        self.assertEqual(self.store.clear(self.a, "a"*64, 2), 3)
        with self.assertRaises(RevisionConflict):
            self.store.clear(self.a, "a"*64, 2)

    def test_concurrent_updates(self):
        def attempt(_):
            try:
                self.store.write(self.a, "a"*64, 0, self.data)
                return True
            except RevisionConflict:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_validation_and_history_consent(self):
        self.assertIsNone(json.loads(normalize_extended(EMPTY))["history"])
        self.assertEqual(json.loads(normalize_extended({**EMPTY, "history": []}))["history"], [])
        for bad in (
            {**self.data, "albums": ["/local/file"]},
            {**self.data, "artists": ["LA123"]},
            {**self.data, "token": "secret"},
            {**self.data, "history": self.data["history"] * 2},
            {**self.data, "history": [{**self.data["history"][0], "played_ms": True}]},
            {**self.data, "history": [{**self.data["history"][0], "song_id": "/local/path"}]},
        ):
            with self.assertRaises(ValueError):
                normalize_extended(bad)

if __name__ == "__main__":
    unittest.main()
