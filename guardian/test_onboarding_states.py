import unittest
from guardian import test_account_protocol_v2 as fixture_module
from guardian.test_account_protocol_v2 import FakeVerifier
from guardian.account_protocol_v2 import AccountProtocol, message
from guardian.device_protocol import b64
from guardian.membership_rules import MembershipDenied
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

class OnboardingStates(unittest.TestCase):
    def setUp(self):
        # Reuse the protocol fixture without importing its test class into discovery.
        self.fixture = fixture_module.ProtocolTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.store = self.fixture.store
        self.api = AccountProtocol(self.store, FakeVerifier(), require_activation=True)

    def role(self, token, key, pub, fp):
        subject = "user_b" if token == "b" else "user_a"
        nonce = self.api.challenge(token, pub, "identity_role", {})["nonce"]
        sig = b64(key.sign(message(nonce, fp, "sess_a", subject, "identity_role", {}),
                           ec.ECDSA(hashes.SHA256())))
        return self.api.execute(token, pub, nonce, sig, "identity_role", {})

    def test_linked_and_recovery_are_distinct(self):
        self.assertEqual(self.role("a", self.fixture.key, self.fixture.pub, self.fixture.fp)["onboarding"], "linked")
        self.assertEqual(self.role("a", self.fixture.other, self.fixture.other_pub, self.fixture.other_fp)["onboarding"], "recovery_required")

    def test_missing_activation_config(self):
        role = self.role("b", self.fixture.other, self.fixture.other_pub, self.fixture.other_fp)
        self.assertEqual(role["onboarding"], "configuration_required")
        self.assertFalse(role["activation_available"])

    def test_other_account_device_conflict(self):
        self.assertEqual(self.role("b", self.fixture.key, self.fixture.pub, self.fixture.fp)["onboarding"], "device_conflict")

    def test_legacy_paths_closed(self):
        for action, body in (("register", {}), ("redeem_free", {"code": "a"*43})):
            with self.subTest(action=action), self.assertRaises(MembershipDenied):
                self.api.challenge("b", self.fixture.other_pub, action, body)

    def test_owner_setup_vs_existing_owner(self):
        class Owner:
            def role(self, session):
                return "owner" if session.subject == "user_b" else "member"
        self.api.owner_bootstrap = Owner()
        role = self.role("b", self.fixture.other, self.fixture.other_pub, self.fixture.other_fp)
        self.assertEqual(role["role"], "owner")
        self.assertEqual(role["onboarding"], "owner_setup")
        self.assertTrue(role["owner_configured"])

