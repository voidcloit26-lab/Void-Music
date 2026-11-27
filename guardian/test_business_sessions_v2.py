import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import contextmanager
from guardian.business_store import BusinessDenied
from guardian.business_sessions_v2 import BusinessSessions

class Store:
    def __init__(self,path):
        self.path=path
        with self.transaction() as db:
            db.execute("CREATE TABLE business_session_v2 (singleton INTEGER PRIMARY KEY,digest BLOB,issued_at INTEGER,expires_at INTEGER)")
            db.execute("CREATE TABLE business_login_budget_v2 (singleton INTEGER PRIMARY KEY,window_start INTEGER,used INTEGER)")
    @contextmanager
    def transaction(self):
        conn=sqlite3.connect(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

class SessionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.salt=b"s"*32
        cls.password="synthetic-test-password"
        cls.digest=BusinessSessions.password_hash(cls.password,cls.salt)

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=Store(str(Path(tmp.name)/"db"))
        self.now=1800000000
        self.sessions=self.new()
    def new(self):
        return BusinessSessions(self.store,owner_id="qa_owner",salt=self.salt,digest=self.digest,scope=b"x"*32,clock=lambda:self.now)

    def login(self):
        return self.sessions.login("qa_owner",self.password)

    def test_durable_session_and_digest_only(self):
        token=self.login()
        self.assertEqual(self.new().verify(token),("qa_owner",self.now))
        with self.store.transaction() as db:
            stored=db.execute("SELECT digest FROM business_session_v2").fetchone()[0]
        self.assertEqual(len(stored),32)
        self.assertNotEqual(stored,token.encode())

    def test_expiry_and_backward_clock(self):
        token=self.login()
        self.now-=1
        with self.assertRaises(BusinessDenied): self.sessions.verify(token)
        self.now+=301
        with self.assertRaises(BusinessDenied): self.sessions.verify(token)

    def test_replacement_and_logout(self):
        old=self.login()
        new=self.login()
        with self.assertRaises(BusinessDenied): self.sessions.verify(old)
        self.assertFalse(self.sessions.logout(old))
        self.assertEqual(self.sessions.verify(new)[0],"qa_owner")
        self.assertTrue(self.sessions.logout(new))
        with self.assertRaises(BusinessDenied): self.sessions.verify(new)

    def test_shared_login_budget(self):
        for _ in range(3):
            with self.assertRaises(BusinessDenied): self.new().login("wrong",self.password)
        with self.assertRaises(BusinessDenied): self.login()
        self.now+=60
        self.assertEqual(self.sessions.verify(self.login())[0],"qa_owner")

    def test_customer_token_rejected(self):
        with self.assertRaises(BusinessDenied): self.sessions.verify("header.claims.signature")
        with self.assertRaises(BusinessDenied): self.sessions.verify("a"*43)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            BusinessSessions(self.store,owner_id="qa_owner",salt=b"",digest=self.digest,scope=b"x"*32)

if __name__=="__main__":
    unittest.main()
