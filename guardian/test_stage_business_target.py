import unittest
from guardian.stage_target import business_connection_options, connection_options, BUSINESS_ROLE, ROLE
from guardian.stage_business_store import StageBusinessStore


def url(role):
    return f"postgresql://{role}:synthetic@ep-example.ap-southeast-1.aws.neon.tech/void_guardian_v2_stage?sslmode=verify-full&channel_binding=require"


class StageBusinessTargetTests(unittest.TestCase):
    def test_business_role_only(self):
        self.assertEqual(business_connection_options(url(BUSINESS_ROLE))["user"], BUSINESS_ROLE)
        with self.assertRaises(ValueError):
            business_connection_options(url(ROLE))

    def test_customer_role_only(self):
        self.assertEqual(connection_options(url(ROLE))["user"], ROLE)
        with self.assertRaises(ValueError):
            connection_options(url(BUSINESS_ROLE))

    def test_wrong_database(self):
        with self.assertRaises(ValueError):
            business_connection_options(url(BUSINESS_ROLE).replace("void_guardian_v2_stage?", "void_guardian?"))

    def test_no_tls_downgrade(self):
        with self.assertRaises(ValueError):
            business_connection_options(url(BUSINESS_ROLE).replace("verify-full", "require"))

    def test_explicit_sandbox_and_verifier_required(self):
        with self.assertRaises(PermissionError):
            StageBusinessStore(url(BUSINESS_ROLE), b"x"*32, owner_id="owner", verify_owner=lambda _: None)
        with self.assertRaises(ValueError):
            StageBusinessStore(url(BUSINESS_ROLE), b"x"*32, sandbox=True, owner_id="owner", verify_owner=None)


if __name__ == "__main__":
    unittest.main()
