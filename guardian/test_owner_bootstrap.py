import tempfile
import unittest
from pathlib import Path
from guardian.account_protocol_v2 import LinkedCloudStore
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.owner_bootstrap import OwnerBootstrap
from guardian.clerk_session import VerifiedSession
from guardian.membership_rules import MembershipDenied

class OwnerBootstrapTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.issuer="https://example.clerk.accounts.dev"
        self.store=LinkedCloudStore(str(Path(tmp.name)/"qa.sqlite"),b"x"*32,issuer=self.issuer)
        self.policy=OwnerIdentityPolicy(self.issuer,{"user_owner":"owner@gmail.com"})
        self.profile={"id":"user_owner","primary_email_address_id":"id_1","email_addresses":[{"id":"id_1","email_address":"owner@gmail.com","verification":{"status":"verified"}}]}
        self.bootstrap=OwnerBootstrap(self.store,self.policy,lambda _:self.profile)
        self.session=VerifiedSession(self.issuer,"user_owner","sess_test")
    def test_owner_lifetime_and_recovery(self):
        a,r,m=self.bootstrap.register(self.session,"a"*64)
        self.assertEqual(m.kind,"lifetime")
        self.assertEqual(self.store.recover_linked(self.issuer,"user_owner",r,"b"*64)[0],a)
        self.assertEqual(self.store.membership(a,"b"*64).kind,"lifetime")
    def test_regular_user_denied(self):
        other=VerifiedSession(self.issuer,"user_other","sess_test")
        self.assertEqual(self.bootstrap.role(other),"member")
        with self.assertRaises(MembershipDenied): self.bootstrap.register(other,"a"*64)
    def test_unverified_owner_denied(self):
        self.profile["email_addresses"][0]["verification"]["status"]="unverified"
        with self.assertRaises(MembershipDenied): self.bootstrap.register(self.session,"a"*64)
    def test_duplicate_bootstrap(self):
        self.bootstrap.register(self.session,"a"*64)
        with self.assertRaises(MembershipDenied): self.bootstrap.register(self.session,"b"*64)
if __name__=="__main__": unittest.main()
