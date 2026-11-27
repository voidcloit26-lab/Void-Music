import unittest
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.clerk_session import VerifiedSession
from guardian.business_store import BusinessDenied

class OwnerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.issuer="https://example.clerk.accounts.dev"
        self.policy=OwnerIdentityPolicy(self.issuer,{"user_owner":"owner@gmail.com"})
        self.session=VerifiedSession(self.issuer,"user_owner","sess_test")
        self.profile={"id":"user_owner","primary_email_address_id":"id_1","email_addresses":[{"id":"id_1","email_address":"owner@gmail.com","verification":{"status":"verified"}}]}
    def test_owner(self):
        self.assertEqual(self.policy.authorize(self.session,self.profile),"user_owner")
    def test_same_email_new_subject(self):
        with self.assertRaises(BusinessDenied):
            self.policy.authorize(VerifiedSession(self.issuer,"user_other","sess_test"),dict(self.profile,id="user_other"))
    def test_unverified_email(self):
        self.profile["email_addresses"][0]["verification"]["status"]="unverified"
        with self.assertRaises(BusinessDenied): self.policy.authorize(self.session,self.profile)
    def test_primary_email_changed(self):
        self.profile["email_addresses"][0]["email_address"]="different@gmail.com"
        with self.assertRaises(BusinessDenied): self.policy.authorize(self.session,self.profile)
    def test_locked_owner(self):
        with self.assertRaises(BusinessDenied): self.policy.authorize(self.session,dict(self.profile,locked=True))
    def test_wrong_issuer(self):
        with self.assertRaises(BusinessDenied): self.policy.authorize(VerifiedSession("https://wrong.test","user_owner","sess_test"),self.profile)
    def test_fresh_mfa(self):
        self.policy.require_fresh_mfa([0,4])
        for value in (None,[0,-1],[5,0],[0,5],[True,0],"0,0"):
            with self.assertRaises(BusinessDenied): self.policy.require_fresh_mfa(value)

if __name__=="__main__": unittest.main()
