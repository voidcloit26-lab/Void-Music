import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy
from guardian.release_registry import ReleaseRegistry

class RegistryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name)/'qa.sqlite')
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.now = 1800000000
        self.registry = ReleaseRegistry(self.path,self.key.public_key(),sandbox=True,clock=lambda:self.now)

    def signed(self, seq, minimum=74, ttl=60):
        p = ReleasePolicy(seq,75,minimum,'1.0.0','a'*64,'b'*64,1234,self.now,self.now+ttl).canonical()
        return p,self.key.sign(p,ec.ECDSA(hashes.SHA256()))

    def test_persistence_and_replay(self):
        self.assertIsNone(self.registry.current())
        signed = self.signed(2)
        self.assertTrue(self.registry.publish(*signed))
        self.assertFalse(self.registry.publish(*signed))
        with self.assertRaises(ValueError):
            self.registry.publish(*self.signed(1))
        with self.assertRaises(ValueError):
            self.registry.publish(*self.signed(2,75))
        reopened=ReleaseRegistry(self.path,self.key.public_key(),sandbox=True,clock=lambda:self.now)
        self.assertEqual(reopened.current(),signed)

    def test_expiry_never_falls_back(self):
        self.registry.publish(*self.signed(1,ttl=120))
        self.registry.publish(*self.signed(2,ttl=5))
        self.now+=5
        with self.assertRaises(ValueError):
            self.registry.current()
        self.assertTrue(self.registry.publish(*self.signed(3)))

    def test_wrong_signature(self):
        p,s=self.signed(1)
        with self.assertRaises(InvalidSignature):
            self.registry.publish(p.replace(b'1.0.0',b'1.0.1'),s)
        self.assertIsNone(self.registry.current())

    def test_concurrent_publish(self):
        signed=self.signed(1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(lambda _: self.registry.publish(*signed),range(8))),1)

    def test_new_sequence_cannot_downgrade_or_substitute(self):
        from dataclasses import replace
        original = ReleasePolicy(1, 75, 74, "1.0.0", "a"*64, "b"*64, 1234, self.now, self.now+120)
        def publish(policy):
            payload = policy.canonical()
            return self.registry.publish(payload, self.key.sign(payload, ec.ECDSA(hashes.SHA256())))
        self.assertTrue(publish(original))
        for change in (
            {"latest":74}, {"minimum":73}, {"signer_sha256":"c"*64},
            {"apk_sha256":"c"*64}, {"apk_bytes":1235}, {"version_name":"1.0.1"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                publish(replace(original, sequence=2, **change))
        self.assertTrue(publish(replace(original, sequence=2, expires_at=self.now+240)))
        self.assertTrue(publish(replace(original, sequence=3, latest=76, minimum=76,
                                        version_name="1.0.1", apk_sha256="d"*64)))
        self.assertEqual(self.registry.current()[0],
                         replace(original, sequence=3, latest=76, minimum=76,
                                 version_name="1.0.1", apk_sha256="d"*64).canonical())

    def test_requires_sandbox(self):
        with self.assertRaises(PermissionError):
            ReleaseRegistry(self.path,self.key.public_key())
