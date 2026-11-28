import unittest
from contextlib import contextmanager
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy
from guardian.stage_release_registry import StageReleaseRegistry, ReleaseUnavailable


class FakeStore:
    def __init__(self, *, write=False, read=True):
        self.write, self.read, self.row = write, read, None

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, sql, params=()):
        class Result:
            def __init__(self, row):
                self.row = row
            def fetchone(self):
                return self.row
        if "LIMIT 0" in sql:
            return Result(None)
        if "has_table_privilege" in sql:
            return Result((self.read if "'SELECT'" in sql else self.write,))
        if "ORDER BY sequence DESC LIMIT 1" in sql:
            return Result(self.row)
        raise AssertionError("unexpected query")


class StageReleaseRegistryTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.store = FakeStore()
        self.registry = StageReleaseRegistry(self.store,self.key.public_key(),clock=lambda:self.now)

    def publish(self, ttl=120):
        policy = ReleasePolicy(1,75,74,"1.0.1","a"*64,"b"*64,1024,self.now,self.now+ttl)
        raw = policy.canonical()
        signature = self.key.sign(raw,ec.ECDSA(hashes.SHA256()))
        self.store.row = (policy.sequence,raw,signature)
        return raw, signature

    def test_empty_and_valid(self):
        self.assertIsNone(self.registry.current())
        expected = self.publish()
        self.assertEqual(self.registry.current(), expected)

    def test_denies_write_grants_and_missing_read(self):
        for store in (FakeStore(write=True), FakeStore(read=False)):
            with self.assertRaises(PermissionError):
                StageReleaseRegistry(store,self.key.public_key())

    def test_wrong_sequence(self):
        raw,sig = self.publish()
        self.store.row = (2,raw,sig)
        with self.assertRaises(ReleaseUnavailable):
            self.registry.current()

    def test_tampered_signature_or_payload(self):
        raw,sig = self.publish()
        self.store.row = (1,raw.replace(b'1.0.1',b'1.0.2'),sig)
        with self.assertRaises(ReleaseUnavailable):
            self.registry.current()

    def test_expired_policy_never_grants(self):
        self.publish()
        self.now += 120
        with self.assertRaises(ReleaseUnavailable):
            self.registry.current()
