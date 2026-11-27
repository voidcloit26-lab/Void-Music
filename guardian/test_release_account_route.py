import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.account_protocol_v2 import AccountProtocol, LinkedCloudStore, message
from guardian.access_store import AccessDenied
from guardian.device_protocol import b64, unb64
from guardian.membership_rules import MembershipDenied
from guardian.release_policy import ReleasePolicy, verify_policy
from guardian.release_registry import ReleaseRegistry
from guardian.test_account_protocol_v2 import FakeVerifier, ISSUER, device


class ReleaseAccountRouteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.store = LinkedCloudStore(str(root / "accounts.sqlite"), b"x"*32, issuer=ISSUER)
        self.key, self.pub, self.fp = device()
        _, self.other_pub, _ = device()
        self.account, self.recovery = self.store.create_account(self.fp)
        self.store.link(self.account, self.fp, ISSUER, "user_a")
        self.release_key = ec.generate_private_key(ec.SECP256R1())
        self.registry = ReleaseRegistry(str(root / "release.sqlite"), self.release_key.public_key(), sandbox=True)
        self.api = AccountProtocol(self.store, FakeVerifier())

    def publish(self):
        now = self.store._now()
        policy = ReleasePolicy(1, 74, 73, "1.0.0", "a"*64, "b"*64, 1024, now, now+3600)
        payload = policy.canonical()
        sig = self.release_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        self.registry.publish(payload, sig)
        return policy

    def proof(self):
        nonce = self.api.challenge("a", self.pub, "release_policy", {})["nonce"]
        sig = b64(self.key.sign(message(nonce, self.fp, "sess_a", "user_a", "release_policy", {}), ec.ECDSA(hashes.SHA256())))
        return nonce, sig

    def test_disabled_without_registry(self):
        with self.assertRaises(MembershipDenied):
            self.api.challenge("a", self.pub, "release_policy", {})

    def test_requires_linked_device_and_identity(self):
        self.api.release_registry = self.registry
        for token, pub in [("b", self.pub), ("a", self.other_pub)]:
            with self.assertRaises(MembershipDenied):
                self.api.challenge(token, pub, "release_policy", {})

    def test_missing_policy_denied(self):
        self.api.release_registry = self.registry
        nonce, sig = self.proof()
        with self.assertRaises(MembershipDenied):
            self.api.execute("a", self.pub, nonce, sig, "release_policy", {})

    def test_signed_policy_and_replay(self):
        policy = self.publish()
        self.api.release_registry = self.registry
        nonce, sig = self.proof()
        with self.assertRaises(AccessDenied):
            self.api.execute("other_session", self.pub, nonce, sig, "release_policy", {})
        result = self.api.execute("a", self.pub, nonce, sig, "release_policy", {})
        self.assertEqual(set(result), {"payload", "signature", "server_time"})
        actual = verify_policy(unb64(result["payload"]), unb64(result["signature"]),
                               self.release_key.public_key(), result["server_time"])
        self.assertEqual(actual, policy)
        with self.assertRaises(AccessDenied):
            self.api.execute("a", self.pub, nonce, sig, "release_policy", {})
