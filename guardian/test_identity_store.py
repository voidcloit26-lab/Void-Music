import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from guardian.identity_store import IdentityStore
from guardian.membership_rules import MembershipDenied

class IdentityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1800000000
        self.path = str(Path(self.temp.name) / "test.sqlite")
        self.store = IdentityStore(self.path, b"x"*32, clock=lambda: self.now)
        self.a, self.recovery = self.store.create_account("a"*64)
        self.b, self.other = self.store.create_account("b"*64)

    def test_recovery_preserves_membership_and_rotates(self):
        key = self.store.issue_free(self.a,"lifetime")
        original = self.store.redeem(self.a,"a"*64,key)
        new = self.store.recover(self.a,self.recovery,"c"*64)
        self.assertNotEqual(new,self.recovery)
        self.assertEqual(self.store.membership(self.a,"c"*64),original)
        with self.assertRaises(MembershipDenied):
            self.store.membership(self.a,"a"*64)
        with self.assertRaises(MembershipDenied):
            self.store.recover(self.a,self.recovery,"d"*64)

    def test_wrong_account_and_device(self):
        key = self.store.issue_free(self.a,"lifetime")
        for account,device in ((self.b,"b"*64),(self.a,"b"*64)):
            with self.assertRaises(MembershipDenied):
                self.store.redeem(account,device,key)
        self.assertEqual(self.store.redeem(self.a,"a"*64,key).kind,"lifetime")

    def test_concurrent_redemption(self):
        key = self.store.issue_free(self.a,"lifetime")
        def redeem(_):
            try:
                self.store.redeem(self.a,"a"*64,key)
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(redeem,range(4))),1)

    def test_expiry_and_revocation(self):
        key = self.store.issue_free(self.a,"trial",days=1,ttl=1)
        self.now += 1
        with self.assertRaises(MembershipDenied):
            self.store.redeem(self.a,"a"*64,key)
        key = self.store.issue_free(self.a,"trial",days=1)
        result = self.store.redeem(self.a,"a"*64,key)
        upgrade = self.store.issue_free(self.a,"lifetime")
        self.assertTrue(self.store.set_state(self.a,"revoked"))
        with self.assertRaises(MembershipDenied):
            self.store.redeem(self.a,"a"*64,upgrade)
        self.assertEqual(self.store.membership(self.a,"a"*64).status(self.now),"revoked")

    def test_collision_and_paid_disabled(self):
        with self.assertRaises(MembershipDenied):
            self.store.create_account("a"*64)
        with self.assertRaises(MembershipDenied):
            self.store.recover(self.a,self.recovery,"b"*64)
        for kind in ("annual","renewal"):
            with self.assertRaises(MembershipDenied):
                self.store.issue_free(self.a,kind)
        self.store.recover(self.a,self.recovery,"c"*64)

    def test_reopen(self):
        key = self.store.issue_free(self.a,"lifetime")
        original = self.store.redeem(self.a,"a"*64,key)
        reopened = IdentityStore(self.path,b"x"*32,clock=lambda:self.now)
        self.assertEqual(reopened.membership(self.a,"a"*64),original)
        with self.assertRaises(MembershipDenied):
            reopened.redeem(self.a,"a"*64,key)
