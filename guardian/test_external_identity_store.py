import tempfile
import unittest
from pathlib import Path
from guardian.external_identity_store import ExternalIdentityStore
from guardian.membership_rules import MembershipDenied

class ExternalIdentityTests(unittest.TestCase):
    issuer="https://example.clerk.accounts.dev"
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store=ExternalIdentityStore(str(Path(temp.name)/"qa.sqlite"),b"x"*32,issuer=self.issuer)
        self.a,self.recovery=self.store.create_account("a"*64)
        self.b,_=self.store.create_account("b"*64)

    def test_link_and_resolve(self):
        self.assertTrue(self.store.link(self.a,"a"*64,self.issuer,"user_abc"))
        self.assertFalse(self.store.link(self.a,"a"*64,self.issuer,"user_abc"))
        self.assertEqual(self.store.resolve(self.issuer,"user_abc","a"*64),self.a)
        self.assertIsNone(self.store.membership(self.a,"a"*64))

    def test_no_cross_account_link(self):
        self.store.link(self.a,"a"*64,self.issuer,"user_abc")
        for account,device,subject in ((self.b,"b"*64,"user_abc"),(self.a,"a"*64,"user_other"),(self.a,"b"*64,"user_abc")):
            with self.assertRaises(MembershipDenied):
                self.store.link(account,device,self.issuer,subject)

    def test_reject_other_issuer_and_unknown_identity(self):
        with self.assertRaises(MembershipDenied):
            self.store.link(self.a,"a"*64,"https://other.example","user_abc")
        with self.assertRaises(MembershipDenied):
            self.store.resolve(self.issuer,"user_abc","a"*64)

    def test_recovery_preserves_link_and_membership(self):
        self.store.link(self.a,"a"*64,self.issuer,"user_abc")
        original=self.store.redeem(self.a,"a"*64,self.store.issue_free(self.a,"lifetime"))
        self.store.recover(self.a,self.recovery,"c"*64)
        with self.assertRaises(MembershipDenied):
            self.store.resolve(self.issuer,"user_abc","a"*64)
        self.assertEqual(self.store.resolve(self.issuer,"user_abc","c"*64),self.a)
        self.assertEqual(self.store.membership(self.a,"c"*64),original)
