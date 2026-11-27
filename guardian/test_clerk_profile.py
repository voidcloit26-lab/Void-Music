import unittest
from guardian.clerk_profile import ClerkProfileLookup, verified_primary_email
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
if __name__=="__main__": unittest.main()
