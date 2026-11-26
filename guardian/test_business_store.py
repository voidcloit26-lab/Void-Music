import tempfile
import unittest
from pathlib import Path
from guardian.business_store import BusinessStore, BusinessDenied
from guardian.membership_rules import MembershipDenied

class BusinessTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=str(Path(tmp.name)/"qa.sqlite")
        self.now=1800000000
        self.auth_time=self.now
        def verify(token):
            if token=="owner":
                return "admin",self.auth_time
            if token=="customer":
                return "customer",self.now
            raise ValueError("invalid credential")
        self.verify=verify
        self.s=BusinessStore(self.path,b"x"*32,sandbox=True,owner_id="admin",verify_owner=verify,clock=lambda:self.now)
        self.a,_=self.s.create_account("a"*64)

    def test_owner_only_and_freshness(self):
        for token in ("customer","invalid"):
            with self.assertRaises(BusinessDenied):
                self.s.change_price(token,700)
            with self.assertRaises(BusinessDenied):
                self.s.summary(token)
        self.auth_time-=301
        with self.assertRaises(BusinessDenied):
            self.s.owner_issue_free("owner",self.a,"lifetime")

    def test_sandbox_required(self):
        with self.assertRaises(BusinessDenied):
            BusinessStore(self.path,b"x"*32,owner_id="admin",verify_owner=self.verify)

    def test_price_audited_and_persistent(self):
        self.assertEqual(self.s.price("owner"),500)
        self.s.change_price("owner",700)
        reopened=BusinessStore(self.path,b"x"*32,sandbox=True,owner_id="admin",verify_owner=self.verify,clock=lambda:self.now)
        self.assertEqual(reopened.price("owner"),700)
        self.assertEqual(reopened.audit("owner")[0]["detail"],"500->700")
        with self.assertRaises(ValueError):
            self.s.change_price("owner",True)
        self.assertEqual(len(self.s.audit("owner")),1)

    def test_key_and_audit_redaction(self):
        code=self.s.owner_issue_free("owner",self.a,"lifetime")
        self.assertNotIn(code,str(self.s.audit("owner")))
        self.s.redeem(self.a,"a"*64,code)
        self.assertEqual(self.s.member("owner",self.a)["status"],"active")
        self.assertEqual(self.s.summary("owner")["membership_types"]["lifetime"],1)
        with self.assertRaises(BusinessDenied):
            self.s.owner_issue_free("owner",self.a,"annual")

    def test_suspend_restore_and_revoke(self):
        code=self.s.owner_issue_free("owner",self.a,"trial",days=1)
        self.s.redeem(self.a,"a"*64,code)
        self.s.change_state("owner",self.a,"suspended")
        self.assertEqual(self.s.member("owner",self.a)["status"],"suspended")
        self.s.change_state("owner",self.a,"enabled")
        self.assertEqual(self.s.member("owner",self.a)["status"],"active")
        self.s.change_state("owner",self.a,"revoked")
        with self.assertRaises(BusinessDenied):
            self.s.change_state("owner",self.a,"enabled")
        self.assertEqual(len(self.s.audit("owner")),4)

    def test_failed_issue_has_no_audit(self):
        with self.assertRaises(MembershipDenied):
            self.s.owner_issue_free("owner","b"*32,"lifetime")
        self.assertEqual(self.s.audit("owner"),[])
        self.assertFalse(self.s.summary("owner")["payments_enabled"])
