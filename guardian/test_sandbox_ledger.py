import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.sandbox_ledger import SandboxLedger
from guardian.membership_rules import MembershipDenied, annual_end

class SandboxLedgerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = str(Path(temp.name)/"test.sqlite")
        self.now = 1800000000
        self.s = SandboxLedger(self.path,b"x"*32,sandbox=True,clock=lambda:self.now)
        self.a,_ = self.s.create_account("a"*64)
        self.b,_ = self.s.create_account("b"*64)

    def receipt(self,n=1):
        return self.s.record_test_payment(self.a,"test:"+format(n,"064x"),500)

    def test_gate_and_validation(self):
        with self.assertRaises(PermissionError):
            SandboxLedger(self.path,b"x"*32)
        with self.assertRaises(ValueError):
            self.s.record_test_payment(self.a,"a"*64,500)
        with self.assertRaises(MembershipDenied):
            self.s.record_test_payment(self.a,"test:"+"a"*64,499)

    def test_duplicate_receipt(self):
        p=self.receipt()
        self.assertEqual(self.receipt(),p)
        with self.assertRaises(MembershipDenied):
            self.s.record_test_payment(self.b,"test:"+format(1,"064x"),500)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(set(pool.map(lambda _:self.receipt(),range(8))),{p})

    def test_issue_redeem_and_renew(self):
        p=self.receipt()
        key=self.s.issue_paid_test_key(p)
        with self.assertRaises(MembershipDenied):
            self.s.issue_paid_test_key(p)
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.b,"b"*64,key)
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.a,"b"*64,key)
        member=self.s.redeem_paid_test(self.a,"a"*64,key)
        self.assertEqual(member.expires_at,annual_end(self.now))
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.a,"a"*64,key)
        with self.assertRaises(MembershipDenied):
            self.s.issue_paid_test_key(p)
        renewal=self.s.issue_paid_test_key(self.receipt(2))
        extended=self.s.redeem_paid_test(self.a,"a"*64,renewal)
        self.assertEqual(extended.expires_at,annual_end(member.expires_at))

    def test_expired_key_reissue(self):
        p=self.receipt()
        old=self.s.issue_paid_test_key(p,ttl=1)
        self.now+=1
        new=self.s.issue_paid_test_key(p)
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.a,"a"*64,old)
        self.assertEqual(self.s.redeem_paid_test(self.a,"a"*64,new).kind,"annual")

    def test_void_and_revocation(self):
        p=self.receipt()
        key=self.s.issue_paid_test_key(p)
        self.assertTrue(self.s.void_unredeemed(p))
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.a,"a"*64,key)
        with self.assertRaises(MembershipDenied):
            self.s.issue_paid_test_key(p)
        other=self.receipt(2)
        self.s.redeem_paid_test(self.a,"a"*64,self.s.issue_paid_test_key(other))
        self.assertFalse(self.s.void_unredeemed(other))
        key=self.s.issue_paid_test_key(self.receipt(3))
        self.s.set_state(self.a,"revoked")
        with self.assertRaises(MembershipDenied):
            self.s.redeem_paid_test(self.a,"a"*64,key)

    def test_concurrent_redemption(self):
        key=self.s.issue_paid_test_key(self.receipt())
        def attempt(_):
            try:
                self.s.redeem_paid_test(self.a,"a"*64,key)
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(8))),1)

    def test_lifetime_cannot_be_charged_by_key(self):
        self.s.redeem(self.a,"a"*64,self.s.issue_free(self.a,"lifetime"))
        with self.assertRaises(MembershipDenied):
            self.s.issue_paid_test_key(self.receipt())
