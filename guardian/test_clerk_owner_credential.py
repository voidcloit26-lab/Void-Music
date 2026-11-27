import unittest
from guardian.clerk_session import VerifiedSession
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.clerk_owner_credential import ClerkOwnerCredential
from guardian.business_store import BusinessDenied
class FakeVerifier:
    def __init__(self,session): self.session=session
    def verify(self,token): return self.session
class OwnerCredentialTests(unittest.TestCase):
    def setUp(self):
        self.issuer="https://example.clerk.accounts.dev"
        self.now=1800000000
        self.policy=OwnerIdentityPolicy(self.issuer,{"user_owner":"owner@gmail.com"})
        self.profile={"id":"user_owner","primary_email_address_id":"id_1","email_addresses":[{"id":"id_1","email_address":"owner@gmail.com","verification":{"status":"verified"}}]}
        self.verifier=FakeVerifier(VerifiedSession(self.issuer,"user_owner","sess_test",(0,0),self.now))
        self.auth=ClerkOwnerCredential(self.verifier,self.policy,lambda _:self.profile,clock=lambda:self.now)
    def test_fresh_owner(self):
        self.assertEqual(self.auth("token"),("user_owner",self.now-60))
    def test_customer_denied(self):
        self.verifier.session=VerifiedSession(self.issuer,"user_other","sess_test",(0,0),self.now)
        with self.assertRaises(BusinessDenied): self.auth("token")
    def test_stale_and_missing_factors(self):
        for fva,iat in ((None,self.now),((0,-1),self.now),((4,4),self.now-1),((0,0),self.now-301)):
            self.verifier.session=VerifiedSession(self.issuer,"user_owner","sess_test",fva,iat)
            with self.assertRaises(BusinessDenied): self.auth("token")
    def test_revoked_profile(self):
        self.profile["banned"]=True
        with self.assertRaises(BusinessDenied): self.auth("token")
if __name__=="__main__": unittest.main()
