import tempfile
import unittest
from pathlib import Path
import hashlib
from guardian.clerk_session import VerifiedSession
from guardian.membership_rules import MembershipDenied
from guardian.release_download import DownloadTickets, ReleaseFiles, DownloadUnavailable
from guardian.release_policy import ReleasePolicy
from guardian.external_identity_store import ExternalIdentityStore


class DownloadTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)
        self.now=1800000000
        self.issuer="https://example.clerk.accounts.dev"
        self.store=ExternalIdentityStore(str(self.path/"test.sqlite"),b"x"*32,issuer=self.issuer,clock=lambda:self.now)
        with self.store.transaction() as db:
            db.execute("CREATE TABLE release_downloads_v2 (digest BLOB PRIMARY KEY,identity BLOB UNIQUE,session_digest BLOB,account TEXT,device TEXT,sequence INTEGER,expires_at INTEGER)")
        self.a=VerifiedSession(self.issuer,"user_a","sess_a")
        self.b=VerifiedSession(self.issuer,"user_b","sess_b")
        self.device="a"*64
        self.account,self.recovery=self.store.register(self.issuer,self.a.subject,self.device)
        self.store.redeem(self.account,self.device,self.store.issue_free(self.account,"lifetime"))
        self.tickets=DownloadTickets(self.store)
        self.data=b"synthetic APK content"
        self.digest=hashlib.sha256(self.data).hexdigest()
        self.file=self.path/(self.digest+".apk")
        self.file.write_bytes(self.data)
        self.policy=ReleasePolicy(1,75,74,"1.0.1",self.digest,"b"*64,len(self.data),self.now,self.now+120)
        self.files=ReleaseFiles(self.path)

    def issue(self):
        return self.tickets.issue(self.a,self.account,self.device,1)

    def test_single_use_and_binding(self):
        token=self.issue()
        for session,seq in ((self.b,1),(VerifiedSession(self.issuer,"user_a","sess_new"),1),(self.a,2)):
            with self.assertRaises(MembershipDenied):
                self.tickets.consume(session,token,seq)
        self.tickets.consume(self.a,token,1)
        with self.assertRaises(MembershipDenied):
            self.tickets.consume(self.a,token,1)

    def test_replacement_and_expiry(self):
        first=self.issue()
        second=self.issue()
        with self.assertRaises(MembershipDenied):
            self.tickets.consume(self.a,first,1)
        self.now+=120
        with self.assertRaises(MembershipDenied):
            self.tickets.consume(self.a,second,1)

    def test_recovery_revokes_old_ticket(self):
        token=self.issue()
        self.store.recover_linked(self.issuer,self.a.subject,self.recovery,"b"*64)
        with self.assertRaises(MembershipDenied):
            self.tickets.consume(self.a,token,1)

    def test_suspension_blocks_ticket(self):
        token=self.issue()
        self.store.set_state(self.account,"suspended")
        with self.assertRaises(MembershipDenied):
            self.tickets.consume(self.a,token,1)
        with self.assertRaises(MembershipDenied):
            self.issue()

    def test_verified_file(self):
        with self.files.open_verified(self.policy) as f:
            self.assertEqual(f.read(),self.data)

    def test_tampered_and_truncated(self):
        for data in (b"x"*len(self.data),b"x"):
            self.file.write_bytes(data)
            with self.assertRaises(DownloadUnavailable):
                self.files.open_verified(self.policy)

    def test_symlink_rejected(self):
        self.file.unlink()
        other=self.path/"other.apk"
        other.write_bytes(self.data)
        self.file.symlink_to(other)
        with self.assertRaises(OSError):
            self.files.open_verified(self.policy)
