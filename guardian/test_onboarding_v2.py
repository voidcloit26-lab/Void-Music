import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.account_protocol_v2 import LinkedCloudStore
from guardian.membership_rules import MembershipDenied

class OnboardingTests(unittest.TestCase):
    issuer="https://example.clerk.accounts.dev"
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.s=LinkedCloudStore(str(Path(tmp.name)/"qa.sqlite"),b"x"*32,issuer=self.issuer)

    def register(self,subject="user_new",device="a"*64):
        return self.s.register(self.issuer,subject,device)

    def test_new_account_unactivated(self):
        a,r=self.register()
        self.assertEqual(self.s.resolve(self.issuer,"user_new","a"*64),a)
        self.assertIsNone(self.s.membership(a,"a"*64))
        self.assertEqual(len(r),43)

    def test_duplicate_account_or_device(self):
        self.register()
        for subject,device in (("user_new","b"*64),("user_other","a"*64)):
            with self.assertRaises(MembershipDenied):
                self.register(subject,device)

    def test_recovery_checks_both_factors_and_rotates(self):
        a,r=self.register()
        self.register("user_other","b"*64)
        with self.assertRaises(MembershipDenied):
            self.s.recover_linked(self.issuer,"user_other",r,"c"*64)
        self.s.redeem(a,"a"*64,self.s.issue_free(a,"lifetime"))
        new,rotated=self.s.recover_linked(self.issuer,"user_new",r,"c"*64)
        self.assertEqual(a,new)
        self.assertNotEqual(r,rotated)
        self.assertEqual(self.s.membership(a,"c"*64).kind,"lifetime")
        with self.assertRaises(MembershipDenied):
            self.s.resolve(self.issuer,"user_new","a"*64)
        with self.assertRaises(MembershipDenied):
            self.s.recover_linked(self.issuer,"user_new",r,"d"*64)

    def test_revoked_cannot_recover(self):
        a,r=self.register()
        self.s.redeem(a,"a"*64,self.s.issue_free(a,"lifetime"))
        self.s.set_state(a,"revoked")
        with self.assertRaises(MembershipDenied):
            self.s.recover_linked(self.issuer,"user_new",r,"c"*64)

    def test_concurrent_registration(self):
        def attempt(_):
            try:
                self.register()
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(6))),1)

    def test_lost_response_recovery_rotation(self):
        account,old=self.register()
        new=self.s.rotate_linked_recovery(self.issuer,"user_new","a"*64)
        self.assertNotEqual(old,new)
        with self.assertRaises(MembershipDenied):
            self.s.rotate_linked_recovery(self.issuer,"user_new","b"*64)
        with self.assertRaises(MembershipDenied):
            self.s.recover_linked(self.issuer,"user_new",old,"c"*64)
        self.assertEqual(self.s.recover_linked(self.issuer,"user_new",new,"c"*64)[0],account)
