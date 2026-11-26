import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.durable_challenges import DDL, DurableChallenges, ChallengeDenied

class TestStore:
    def __init__(self, path):
        self.path = path
    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

class DurableChallengeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = TestStore(str(Path(tmp.name)/'qa.sqlite'))
        with self.store.transaction() as db:
            db.execute(DDL)
        self.now = 1800000000
        self.a, self.b = 'a'*64, 'b'*64
        self.first = self.open()
    def open(self, **kwargs):
        return DurableChallenges(self.store, clock=lambda:self.now, **kwargs)
    def proof(self, nonce):
        return ('proof:'+nonce).encode()
    def issue(self):
        return self.first.issue(self.a,self.b,self.proof)
    def test_cross_instance_single_use(self):
        n = self.issue()
        self.open().consume(n,self.a,self.b,self.proof(n))
        with self.assertRaises(ChallengeDenied):
            self.first.consume(n,self.a,self.b,self.proof(n))
    def test_wrong_binding_or_body_does_not_consume(self):
        n = self.issue()
        for a,b,p in (('c'*64,self.b,self.proof(n)),(self.a,'c'*64,self.proof(n)),(self.a,self.b,b'other')):
            with self.assertRaises(ChallengeDenied):
                self.first.consume(n,a,b,p)
        self.first.consume(n,self.a,self.b,self.proof(n))
    def test_expiry_and_slot_reuse(self):
        n = self.issue()
        self.now += 60
        with self.assertRaises(ChallengeDenied):
            self.first.consume(n,self.a,self.b,self.proof(n))
        self.assertNotEqual(n,self.issue())
    def test_concurrent_consumption(self):
        n = self.issue()
        def attempt(_):
            try:
                self.open().consume(n,self.a,self.b,self.proof(n))
                return True
            except ChallengeDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(8))),1)
    def test_bounded_slots(self):
        self.first = self.open(max_pending=2,per_scope=1)
        self.issue()
        with self.assertRaises(ChallengeDenied):
            self.first.issue(self.a,'c'*64,self.proof)
        self.first.issue('c'*64,self.b,self.proof)
        with self.assertRaises(ChallengeDenied):
            self.first.issue('d'*64,self.b,self.proof)
    def test_missing_schema_fails_closed(self):
        with self.store.transaction() as db:
            db.execute('DROP TABLE proof_challenges_v2')
        with self.assertRaises(sqlite3.OperationalError):
            self.open()
