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

if __name__=="__main__": unittest.main()
