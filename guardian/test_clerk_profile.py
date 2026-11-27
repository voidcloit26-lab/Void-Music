import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from guardian.clerk_profile import ClerkProfileLookup, verified_primary_email, ProfileUnavailable
from guardian.clerk_session import SessionDenied

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile={"id":"user_test","primary_email_address_id":"id_1","email_addresses":[
            {"id":"id_1","email_address":"member@gmail.com","verification":{"status":"verified"}}]}
    def test_verified(self):
        self.assertEqual(verified_primary_email("user_test",self.profile),"member@gmail.com")
    def test_unverified(self):
        self.profile["email_addresses"][0]["verification"]["status"]="unverified"
        with self.assertRaises(SessionDenied): verified_primary_email("user_test",self.profile)
    def test_mismatched_identity(self):
        with self.assertRaises(SessionDenied): verified_primary_email("user_other",self.profile)
    def test_locked(self):
        with self.assertRaises(SessionDenied): verified_primary_email("user_test",dict(self.profile,locked=True))
    def test_missing_primary(self):
        with self.assertRaises(SessionDenied): verified_primary_email("user_test",dict(self.profile,primary_email_address_id="other"))
    def test_invalid_secret_and_subject(self):
        with self.assertRaises(ValueError): ClerkProfileLookup("pk_test_not_secret")
        lookup=ClerkProfileLookup("sk_test_synthetic")
        with self.assertRaises(SessionDenied): lookup("../jwks")
    def test_backend_rejection_is_not_user_signout(self):
        lookup = ClerkProfileLookup("sk_test_synthetic")
        with patch.object(lookup._opener, "open", side_effect=HTTPError("https://example.test", 401, "denied", {}, None)):
            with self.assertLogs("guardian.clerk_profile", level="WARNING") as logs:
                with self.assertRaises(ProfileUnavailable):
                    lookup("user_test")
            self.assertIn("401", logs.output[0])
            self.assertNotIn("sk_test_", logs.output[0])
            self.assertNotIn("user_test", logs.output[0])

    def test_network_error_is_not_user_signout(self):
        lookup = ClerkProfileLookup("sk_test_synthetic")
        with patch.object(lookup._opener, "open", side_effect=URLError("private test URL")):
            with self.assertLogs("guardian.clerk_profile", level="WARNING") as logs:
                with self.assertRaises(ProfileUnavailable):
                    lookup("user_test")
            self.assertNotIn("private test URL", logs.output[0])

if __name__=="__main__": unittest.main()
