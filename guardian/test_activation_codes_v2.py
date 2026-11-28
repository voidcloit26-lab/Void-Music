import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from guardian.activation_codes_v2 import ActivationCodes, DDL
from guardian.account_protocol_v2 import LinkedCloudStore
from guardian.business_store import BusinessDenied
from guardian.membership_rules import MembershipDenied, annual_end

class Store(LinkedCloudStore):
    def _owner(self,credential):
        if credential!="owner-test": raise BusinessDenied("denied")
        return "owner"
    def _audit(self,db,*fields):
        db.execute("INSERT INTO test_audit VALUES (?)", (fields[1],))

class ActivationTests(unittest.TestCase):
    issuer="https://example.clerk.accounts.dev"
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.now=1800000000
        self.store=Store(str(Path(temp.name)/"qa.sqlite"),b"x"*32,issuer=self.issuer,clock=lambda:self.now)
        with self.store.transaction() as db:
            db.execute(DDL)
            db.execute("CREATE TABLE test_audit(action TEXT)")
        self.codes=ActivationCodes(self.store)
    def issue(self,kind="lifetime",**kw):
        return self.codes.issue("owner-test",kind,**kw)[0]
    def register(self,code,subject="user_first",device="a"*64):
        return self.codes.register(self.issuer,subject,device,code)
    def test_first_use_and_replay(self):
        code=self.issue()
        a,r,m=self.register(code)
        self.assertEqual(m.kind,"lifetime")
        self.assertEqual(self.store.resolve(self.issuer,"user_first","a"*64),a)
        self.assertEqual(len(r),43)
        with self.assertRaises(MembershipDenied): self.register(code,"user_other","b"*64)
    def test_failed_registration_rolls_back(self):
        with self.assertRaises(MembershipDenied): self.register("x"*43)
        self.assertEqual(self.register(self.issue())[2].kind,"lifetime")
    def test_subject_binding(self):
        code=self.issue(subject="user_first")
        with self.assertRaises(MembershipDenied): self.register(code,"user_other","b"*64)
        self.register(code)
    def test_annual_renewal(self):
        a,_,m=self.register(self.issue("annual"))
        code=self.issue("renewal")
        self.now+=100
        new=self.codes.redeem(self.issuer,"user_first","a"*64,code)
        self.assertEqual(new.expires_at,annual_end(m.expires_at))
        self.now=new.expires_at+100
        later=self.codes.redeem(self.issuer,"user_first","a"*64,self.issue("renewal"))
        self.assertEqual(later.expires_at,annual_end(self.now))
        self.assertEqual(self.store.resolve(self.issuer,"user_first","a"*64),a)
    def test_cancel_and_expiry(self):
        code=self.issue(ttl=1)
        self.now+=1
        with self.assertRaises(MembershipDenied): self.register(code)
        new=self.issue(ttl=None)
        code_id=self.store._digest("activation-v2",new).hex()
        self.assertTrue(self.codes.cancel("owner-test",code_id))
        self.assertFalse(self.codes.cancel("owner-test",code_id))
        with self.assertRaises(MembershipDenied): self.register(new)
    def test_normal_user_cannot_issue(self):
        with self.assertRaises(BusinessDenied): self.codes.issue("member","annual")
        with self.assertRaises(BusinessDenied): self.codes.list("member")
        with self.assertRaises(BusinessDenied): self.codes.cancel("member","a"*64)
    def test_concurrent_first_use(self):
        code=self.issue()
        def attempt(i):
            try:
                self.register(code,"user_test"+str(i),format(i+1,"064x"))
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(6))),1)
    def test_renewal_cannot_create_account(self):
        with self.assertRaises(MembershipDenied): self.register(self.issue("renewal"))
        self.register(self.issue("annual"))
    def test_suspended_cannot_renew(self):
        a,_,_=self.register(self.issue("annual"))
        self.store.set_state(a,"suspended")
        with self.assertRaises(MembershipDenied):
            self.codes.redeem(self.issuer,"user_first","a"*64,self.issue("renewal"))
    def test_batch_and_no_raw_code(self):
        codes=self.codes.issue("owner-test","trial",days=7,count=5)
        self.assertEqual(len(set(codes)),5)
        rows=self.codes.list("owner-test")
        self.assertEqual(len(rows),5)
        self.assertFalse(any(code in str(rows) for code in codes))

    def enable_collective(self):
        from guardian.collective_codes_v3 import DDL, REDEMPTIONS_DDL, INDEX_DDL
        with self.store.transaction() as db:
            for sql in (DDL, REDEMPTIONS_DDL, INDEX_DDL):
                db.execute(sql)
        self.codes.collective = True

    def test_collective_cap_and_history(self):
        self.enable_collective()
        code = self.issue("annual", claim_limit=2)
        a, _, _ = self.register(code)
        b, _, _ = self.register(code, "user_second", "b"*64)
        with self.assertRaises(MembershipDenied):
            self.register(code, "user_third", "c"*64)
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT used_count FROM collective_codes_v3").fetchone()[0], 2)
            rows = db.execute("SELECT account,new_expiry FROM collective_redemptions_v3").fetchall()
            self.assertEqual({r[0] for r in rows}, {a,b})
            self.assertTrue(all(r[1] == annual_end(self.now) for r in rows))

    def test_collective_renewal_once_per_account(self):
        self.enable_collective()
        _, _, old = self.register(self.issue("annual"))
        code = self.issue("renewal", claim_limit=5)
        new = self.codes.redeem(self.issuer, "user_first", "a"*64, code)
        self.assertEqual(new.expires_at, annual_end(old.expires_at))
        with self.assertRaises(MembershipDenied):
            self.codes.redeem(self.issuer, "user_first", "a"*64, code)
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT used_count FROM collective_codes_v3").fetchone()[0], 1)

    def test_collective_concurrent_cap(self):
        self.enable_collective()
        code = self.issue("annual", claim_limit=3)
        def attempt(i):
            try:
                self.register(code, "user_c"+str(i), format(i+1,"064x"))
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 3)

    def test_collective_cancel_expiry_and_disabled(self):
        with self.assertRaises(ValueError):
            self.issue("annual", claim_limit=2)
        self.enable_collective()
        code = self.issue("annual", claim_limit=3)
        self.register(code)
        self.assertTrue(self.codes.cancel("owner-test", self.store._digest("activation-v2",code).hex()))
        with self.assertRaises(MembershipDenied):
            self.register(code, "user_other", "b"*64)
        expired = self.issue("annual", claim_limit=2, ttl=1)
        self.now += 1
        with self.assertRaises(MembershipDenied):
            self.register(expired, "user_other", "b"*64)

    def test_collective_rejects_subject_and_batch(self):
        self.enable_collective()
        for args in ({"subject":"user_first"}, {"count":2}, {"claim_limit":101}):
            with self.assertRaises(ValueError):
                self.codes.issue("owner-test", "annual", **({"claim_limit":2} | args))

    def test_owner_claim_history_includes_single_and_collective(self):
        self.enable_collective()
        account, _, _ = self.register(self.issue("annual"))
        self.now += 1
        shared = self.issue("renewal", claim_limit=2)
        self.codes.redeem(self.issuer,"user_first","a"*64,shared)
        history = self.codes.history("owner-test",account)
        self.assertEqual(history["total_claims"],2)
        self.assertEqual(history["renewals"],1)
        self.assertEqual([event["claim_number"] for event in history["events"]],[2,1])
        self.assertTrue(history["events"][0]["collective"])
        self.assertFalse(history["events"][1]["collective"])
        self.assertNotIn(shared,str(history))
        with self.assertRaises(BusinessDenied):
            self.codes.history("member",account)
        with self.assertRaises(MembershipDenied):
            self.codes.history("owner-test","f"*32)

if __name__=="__main__": unittest.main()
