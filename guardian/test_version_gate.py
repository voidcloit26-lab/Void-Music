import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy
from guardian.release_registry import ReleaseRegistry
from guardian.version_gate import VersionGate, UpdateRequired


class VersionGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1800000000
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.registry = ReleaseRegistry(str(Path(tmp.name)/"release.sqlite"), self.key.public_key(),
                                        sandbox=True, clock=lambda:self.now)
        self.gate = VersionGate(self.registry)
        self.policy = ReleasePolicy(1,75,74,"1.0.1","a"*64,"b"*64,1024,self.now,self.now+120)

    def publish(self, policy):
        payload = policy.canonical()
        self.registry.publish(payload, self.key.sign(payload, ec.ECDSA(hashes.SHA256())))

    def test_missing_policy_does_not_grant(self):
        with self.assertRaises(RuntimeError):
            self.gate.require_supported(74,"b"*64)

    def test_supported_range(self):
        self.publish(self.policy)
        for version in (74,75):
            self.assertEqual(self.gate.require_supported(version,"b"*64), self.policy)
        for version in (73,76):
            with self.subTest(version=version), self.assertRaises(UpdateRequired):
                self.gate.require_supported(version,"b"*64)

    def test_wrong_signer(self):
        self.publish(self.policy)
        with self.assertRaises(UpdateRequired):
            self.gate.require_supported(75,"c"*64)

    def test_invalid_input(self):
        for version,signer in ((True,"b"*64),(0,"b"*64),(75,"bad"),(75,None)):
            with self.subTest(version=version,signer=signer), self.assertRaises(ValueError):
                self.gate.require_supported(version,signer)

    def test_new_mandatory_release(self):
        self.publish(self.policy)
        newer = replace(self.policy, sequence=2, minimum=76, latest=76,
                        version_name="1.0.2", apk_sha256="c"*64)
        self.publish(newer)
        with self.assertRaises(UpdateRequired):
            self.gate.require_supported(75,"b"*64)
        self.assertEqual(self.gate.require_supported(76,"b"*64),newer)

    def test_expired_policy_does_not_grant(self):
        self.publish(self.policy)
        self.now += 120
        with self.assertRaises(ValueError):
            self.gate.require_supported(75,"b"*64)
