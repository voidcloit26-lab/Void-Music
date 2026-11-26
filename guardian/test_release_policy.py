import unittest
from dataclasses import replace
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy, verify_policy

class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = 1700000000
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.policy = ReleasePolicy(1, 74, 74, "1.0.0", "a"*64, "b"*64,
                                    70000000, self.now, self.now + 3600)

    def verify(self, policy, previous=None):
        payload = policy.canonical()
        sig = self.key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return verify_policy(payload, sig, self.key.public_key(), self.now, previous)

    def test_mandatory_and_current(self):
        p = self.verify(self.policy)
        self.assertEqual(p.decision(73), "required")
        self.assertEqual(p.decision(74), "current")
        self.assertEqual(p.decision(75), "current")

    def test_optional_and_emergency_policy(self):
        p = self.verify(replace(self.policy, sequence=2, minimum=73), self.policy)
        self.assertEqual(p.decision(73), "available")

    def test_replay_and_sequence_reuse(self):
        with self.assertRaises(ValueError):
            self.verify(self.policy, replace(self.policy, sequence=2))
        with self.assertRaises(ValueError):
            self.verify(replace(self.policy, minimum=73), self.policy)
        self.assertEqual(self.verify(self.policy, self.policy), self.policy)

    def test_invalid_signature(self):
        payload = self.policy.canonical()
        sig = self.key.sign(payload, ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(InvalidSignature):
            verify_policy(replace(self.policy, minimum=73).canonical(), sig,
                          self.key.public_key(), self.now)

    def test_invalid_metadata(self):
        for policy in (replace(self.policy, expires_at=self.now),
                       replace(self.policy, minimum=75),
                       replace(self.policy, package="other.app"),
                       replace(self.policy, channel="test"),
                       replace(self.policy, apk_sha256="bad"),
                       replace(self.policy, apk_bytes=0),
                       replace(self.policy, latest=True)):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.verify(policy)

if __name__ == "__main__":
    unittest.main()
