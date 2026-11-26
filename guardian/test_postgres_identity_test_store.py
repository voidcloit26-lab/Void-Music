"""Run live integration tests only with an explicitly configured local test DB."""
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from guardian.membership_rules import MembershipDenied, annual_end
from guardian.postgres_identity_test_store import DB, check_target, PostgresIdentityTestStore

class TargetSafetyTests(unittest.TestCase):
    schema="void_v2_test_"+"a"*32
    safe={"host":"127.0.0.1","dbname":DB,"user":DB}

    def test_expected_target(self):
        check_target(self.safe,self.schema,True)

    def test_reject_wrong_targets(self):
        for field,value in (("host","example.com"),("dbname","void_guardian"),
                            ("user","guardian_runtime"),("hostaddr","192.0.2.1"),
                            ("options","-c search_path=public"),("service","production"),
                            ("port","0"),("sslmode","verify-full")):
            with self.subTest(field=field), self.assertRaises((ValueError,PermissionError)):
                check_target({**self.safe,field:value},self.schema,True)

    def test_reject_unsafe_schema_or_implicit_mode(self):
        for schema,mode in (("public",True),("void_guardian",True),(self.schema,False)):
            with self.assertRaises((ValueError,PermissionError)):
                check_target(self.safe,schema,mode)

@unittest.skipUnless(os.getenv("VOID_GUARDIAN_V2_LOCAL_TEST_URL"),"local PostgreSQL not provisioned")
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.url=os.environ["VOID_GUARDIAN_V2_LOCAL_TEST_URL"]
        self.schema="void_v2_test_"+secrets.token_hex(16)
        self.now=1800000000
        self.store=self.open()
        self.addCleanup(self.cleanup)
        self.a,self.recovery=self.store.create_account("a"*64)
        self.b,_=self.store.create_account("b"*64)

    def open(self):
        return PostgresIdentityTestStore(self.url,b"x"*32,schema=self.schema,
                                          sandbox=True,clock=lambda:self.now)

    def cleanup(self):
        # Only the random schema created for this test, on the guarded local DB.
        from psycopg import sql
        with self.store._connection() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def test_lifetime_recovery_and_reopen(self):
        key=self.store.issue_free(self.a,"lifetime")
        old=self.store.redeem(self.a,"a"*64,key)
        self.store.recover(self.a,self.recovery,"c"*64)
        self.assertEqual(self.open().membership(self.a,"c"*64),old)
        with self.assertRaises(MembershipDenied):
            self.store.membership(self.a,"a"*64)

    def test_concurrent_paid_redemption(self):
        payment=self.store.record_test_payment(self.a,"test:"+"a"*64,500)
        key=self.store.issue_paid_test_key(payment)
        def attempt(_):
            try:
                self.open().redeem_paid_test(self.a,"a"*64,key)
                return True
            except MembershipDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(4))),1)
        self.assertEqual(self.store.membership(self.a,"a"*64).expires_at,annual_end(self.now))

    def test_transaction_rollback_and_renewal(self):
        p=self.store.record_test_payment(self.a,"test:"+"b"*64,500)
        key=self.store.issue_paid_test_key(p)
        with self.assertRaises(MembershipDenied):
            self.store.redeem_paid_test(self.b,"b"*64,key)
        member=self.store.redeem_paid_test(self.a,"a"*64,key)
        p=self.store.record_test_payment(self.a,"test:"+"c"*64,500)
        renewed=self.store.redeem_paid_test(self.a,"a"*64,self.store.issue_paid_test_key(p))
        self.assertEqual(renewed.expires_at,annual_end(member.expires_at))
