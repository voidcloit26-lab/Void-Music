import unittest
from guardian.owner_readiness_probe import check_owner_profile
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.clerk_profile import ProfileUnavailable


class OwnerReadinessProbeTests(unittest.TestCase):
    def setUp(self):
        self.policy = OwnerIdentityPolicy("https://example.clerk.accounts.dev", {"user_owner":"owner@gmail.com"})
        self.profile = {"id":"user_owner","primary_email_address_id":"primary","email_addresses":[
            {"id":"primary","email_address":"owner@gmail.com","verification":{"status":"verified"}}]}

    def test_verified_read_only(self):
        with self.assertLogs("guardian.owner_readiness_probe", level="INFO") as logs:
            self.assertTrue(check_owner_profile(self.policy, lambda _: self.profile))
        self.assertIn("verified", logs.output[0])
        self.assertNotIn("owner@gmail.com", logs.output[0])

    def test_lookup_failure_redacted(self):
        def unavailable(_):
            raise ProfileUnavailable("private details")
        with self.assertLogs("guardian.owner_readiness_probe", level="WARNING") as logs:
            self.assertFalse(check_owner_profile(self.policy, unavailable))
        self.assertIn("ProfileUnavailable", logs.output[0])
        self.assertNotIn("private details", logs.output[0])

    def test_unverified_email_denied(self):
        self.profile["email_addresses"][0]["verification"]["status"] = "unverified"
        with self.assertLogs("guardian.owner_readiness_probe", level="WARNING"):
            self.assertFalse(check_owner_profile(self.policy, lambda _: self.profile))
