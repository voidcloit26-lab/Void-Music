import unittest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.membership_rules import Membership, MembershipDenied
from guardian.offline_lease import issue,verify

class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000
        self.key=ec.generate_private_key(ec.SECP256R1())
        self.a='a'*32
        self.d='b'*64

    def read(self, signed, **changes):
        return verify(*signed,self.key.public_key(),**({'account':self.a,'device':self.d,'now':self.now,'trusted_floor':self.now}|changes))

    def test_paid_expiry_caps_lease(self):
        signed=issue(Membership('annual',self.now+10),self.a,self.d,self.now,self.key)
        self.assertEqual(self.read(signed).expires_at,self.now+10)
        with self.assertRaises(ValueError):
            self.read(signed,now=self.now+10)

    def test_lifetime_is_bounded(self):
        signed=issue(Membership('lifetime',None),self.a,self.d,self.now,self.key)
        self.assertEqual(self.read(signed).expires_at,self.now+86400)
        with self.assertRaises(ValueError):
            self.read(signed,now=self.now+86400)

    def test_inactive_cannot_issue(self):
        for m in (Membership('annual',self.now),Membership('lifetime',None,'suspended'),Membership('lifetime',None,'revoked')):
            with self.assertRaises(MembershipDenied):
                issue(m,self.a,self.d,self.now,self.key)

    def test_binding_and_clock(self):
        signed=issue(Membership('lifetime',None),self.a,self.d,self.now,self.key)
        for changes in ({'account':'c'*32},{'device':'d'*64},{'now':self.now-1},{'trusted_floor':0}):
            with self.assertRaises(ValueError):
                self.read(signed,**changes)

    def test_tampering(self):
        payload,sig=issue(Membership('lifetime',None),self.a,self.d,self.now,self.key)
        with self.assertRaises(InvalidSignature):
            self.read((payload.replace(b'"version":2',b'"version":1'),sig))
