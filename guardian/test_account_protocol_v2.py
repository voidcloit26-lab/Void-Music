import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.account_protocol_v2 import AccountProtocol, LinkedCloudStore, message
from guardian.clerk_session import VerifiedSession, SessionDenied
from guardian.device_protocol import b64, read_device_key
from guardian.access_store import AccessDenied
from guardian.membership_rules import MembershipDenied

ISSUER = "https://example.clerk.accounts.dev"

class FakeVerifier:
    def verify(self, token):
        if token not in ("a","b","other_session"):
            raise SessionDenied("invalid")
        return VerifiedSession(ISSUER, "user_b" if token=="b" else "user_a",
                               "sess_other" if token=="other_session" else "sess_a")

def device():
    key=ec.generate_private_key(ec.SECP256R1())
    pub=b64(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    return key,pub,read_device_key(pub)[1]

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=LinkedCloudStore(str(Path(tmp.name)/"test.sqlite"),b"x"*32,issuer=ISSUER)
        self.key,self.pub,self.fp=device()
        self.other,self.other_pub,self.other_fp=device()
        self.account,self.recovery=self.store.create_account(self.fp)
        self.store.link(self.account,self.fp,ISSUER,"user_a")
        self.clock=100
        self.api=AccountProtocol(self.store,FakeVerifier(),clock=lambda:self.clock)

    def prepare(self,action,body):
        nonce=self.api.challenge("a",self.pub,action,body)["nonce"]
        sig=b64(self.key.sign(message(nonce,self.fp,"sess_a","user_a",action,body),ec.ECDSA(hashes.SHA256())))
        return nonce,sig

    def call(self,action,body):
        nonce,sig=self.prepare(action,body)
        return self.api.execute("a",self.pub,nonce,sig,action,body)

    def test_status_redeem_and_cloud(self):
        self.assertEqual(self.call("status",{})["status"],"unactivated")
        code=self.store.issue_free(self.account,"lifetime")
        self.call("redeem_free",{"code":code})
        self.assertEqual(self.call("status",{})["status"],"active")
        data={"favorites":["track"],"playlists":[],"preferences":{}}
        self.assertEqual(self.call("cloud_write",{"revision":0,"library":data}),{"revision":1})
        self.assertEqual(self.call("cloud_read",{})["library"],data)
        self.assertEqual(self.call("cloud_clear",{"revision":1}),{"revision":2})

    def test_invalid_token_device_and_identity(self):
        for token,pub in (("bad",self.pub),("b",self.pub),("a",self.other_pub)):
            with self.assertRaises((SessionDenied,MembershipDenied)):
                self.api.challenge(token,pub,"status",{})

    def test_action_session_and_body_binding(self):
        nonce,sig=self.prepare("cloud_clear",{"revision":0})
        for token,action,body in (("other_session","cloud_clear",{"revision":0}),("a","status",{}),("a","cloud_clear",{"revision":1})):
            with self.assertRaises(AccessDenied):
                self.api.execute(token,self.pub,nonce,sig,action,body)
        self.assertEqual(self.api.execute("a",self.pub,nonce,sig,"cloud_clear",{"revision":0}),{"revision":1})
        with self.assertRaises(AccessDenied):
            self.api.execute("a",self.pub,nonce,sig,"cloud_clear",{"revision":0})

    def test_expired_and_replaced_device(self):
        nonce,sig=self.prepare("status",{})
        self.clock+=60
        with self.assertRaises(AccessDenied):
            self.api.execute("a",self.pub,nonce,sig,"status",{})
        nonce,sig=self.prepare("status",{})
        self.store.recover(self.account,self.recovery,self.other_fp)
        with self.assertRaises(MembershipDenied):
            self.api.execute("a",self.pub,nonce,sig,"status",{})

    def test_concurrent_replay(self):
        nonce,sig=self.prepare("status",{})
        def attempt(_):
            try:
                self.api.execute("a",self.pub,nonce,sig,"status",{})
                return True
            except AccessDenied:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(attempt,range(8))),1)

    def test_signed_lease_requires_active_membership(self):
        from guardian.offline_lease import verify
        from guardian.device_protocol import unb64
        self.api.lease_key=ec.generate_private_key(ec.SECP256R1())
        with self.assertRaises(MembershipDenied):
            self.call("lease",{})
        self.call("redeem_free",{"code":self.store.issue_free(self.account,"lifetime")})
        response=self.call("lease",{})
        now=self.store._now()
        lease=verify(unb64(response["payload"]),unb64(response["signature"]),self.api.lease_key.public_key(),
                     account=self.account,device=self.fp,now=now,trusted_floor=now)
        self.assertLessEqual(lease.expires_at-lease.issued_at,86400)
        self.store.set_state(self.account,"suspended")
        with self.assertRaises(MembershipDenied):
            self.call("lease",{})

    def test_profile_verified_email_and_redemption_counts(self):
        from guardian.activation_codes_v2 import ActivationCodes, DDL
        self.api.activation_codes = ActivationCodes(self.store)
        self.api.profile_lookup = lambda subject: {
            "id": subject, "primary_email_address_id": "id_1",
            "email_addresses": [{"id": "id_1", "email_address": "member@example.com",
                                 "verification": {"status": "verified"}}]}
        with self.store.transaction() as db:
            db.execute(DDL)
            for i, kind in enumerate(("annual", "renewal", "renewal")):
                db.execute("INSERT INTO activation_codes_v2 VALUES (?,?,NULL,NULL,NULL,?,?,NULL)",
                           (bytes([i])*32, kind, self.account, 1800000000+i))
        self.assertEqual(self.call("profile", {}), {
            "account": self.account, "email": "member@example.com", "total_claims": 3, "renewals": 2})
        with self.assertRaises(MembershipDenied):
            self.api.challenge("a", self.other_pub, "profile", {})
        with self.assertRaises(MembershipDenied):
            self.api.challenge("b", self.pub, "profile", {})

    def test_profile_requires_verified_email_and_enabled_activation(self):
        from guardian.activation_codes_v2 import ActivationCodes
        with self.assertRaises(MembershipDenied):
            self.call("profile", {})
        self.api.activation_codes = ActivationCodes(self.store)
        self.api.profile_lookup = lambda subject: {
            "id": subject, "primary_email_address_id": "id_1",
            "email_addresses": [{"id": "id_1", "email_address": "member@example.com",
                                 "verification": {"status": "unverified"}}]}
        with self.assertRaises(SessionDenied):
            self.call("profile", {})
