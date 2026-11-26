import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.shared_budget import DDL, SharedBudget
from guardian.test_durable_challenges import TestStore


class SharedBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = TestStore(str(Path(tmp.name)/'qa.sqlite'))
        with self.store.transaction() as db:
            db.execute(DDL)
        self.now = 1800000000

    def open(self, bucket='account', limit=3):
        return SharedBudget(self.store, bucket=bucket, limit=limit, clock=lambda:self.now)

    def test_persists_across_instances(self):
        self.assertTrue(self.open().take())
        self.assertTrue(self.open().take())
        self.assertTrue(self.open().take())
        self.assertFalse(self.open().take())

    def test_concurrent_limit(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(lambda _:self.open(limit=5).take(),range(20))),5)

    def test_window_reset(self):
        self.assertTrue(self.open(limit=1).take())
        self.now += 59
        self.assertFalse(self.open(limit=1).take())
        self.now += 1
        self.assertTrue(self.open(limit=1).take())

    def test_backward_clock_denied(self):
        self.assertTrue(self.open().take())
        self.now -= 1
        self.assertFalse(self.open().take())

    def test_separate_owner_budget(self):
        self.assertTrue(self.open(limit=1).take())
        self.assertFalse(self.open(limit=1).take())
        self.assertTrue(self.open('owner',1).take())

    def test_invalid_config(self):
        for bucket,limit in [('user-input',1),('account',True),('account',0)]:
            with self.assertRaises(ValueError):
                self.open(bucket,limit)
