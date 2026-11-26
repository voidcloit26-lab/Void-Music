import time
import unittest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from guardian.clerk_session import ClerkSessionVerifier, SessionDenied


class ClerkSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.pem = cls.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.issuer = 'https://void.example'

    def setUp(self):
        self.verifier = ClerkSessionVerifier(issuer=self.issuer,audience='void-music-api',public_key_pem=self.pem,authorized_parties=['https://void.example'])
        now=int(time.time())
        self.claims=dict(iss=self.issuer,aud='void-music-api',sub='user_abc',sid='sess_abc',iat=now,nbf=now,exp=now+60)

    def token(self, changes=None, key=None):
        return jwt.encode({**self.claims,**(changes or {})},key or self.key,algorithm='RS256')

    def test_valid_native_and_allowed_origin(self):
        for token in (self.token(),self.token({'azp':self.issuer})):
            self.assertEqual(self.verifier.verify(token).subject,'user_abc')

    def test_wrong_key_and_algorithm(self):
        for token in (self.token(key=self.other),jwt.encode(self.claims,'x'*32,algorithm='HS256')):
            with self.assertRaises(SessionDenied):
                self.verifier.verify(token)

    def test_claims_rejected(self):
        now=int(time.time())
        for changes in ({'iss':'https://evil.example'},{'aud':'other'},{'azp':'https://evil.example'},{'exp':now-10},{'nbf':now+30},{'iat':now+30},{'exp':now+999},{'sub':'abc'},{'sid':'abc'},{'sts':'pending'},{'act':{'sub':'user_actor'}},{'iat':True}):
            with self.subTest(changes=changes),self.assertRaises(SessionDenied):
                self.verifier.verify(self.token(changes))

    def test_missing_claim_and_invalid_input(self):
        for claim in ('aud','sub','sid','iat','nbf','exp'):
            data={k:v for k,v in self.claims.items() if k!=claim}
            with self.assertRaises(SessionDenied):
                self.verifier.verify(jwt.encode(data,self.key,algorithm='RS256'))
        for token in ('',None,'x'*9000):
            with self.assertRaises(SessionDenied):
                self.verifier.verify(token)

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            ClerkSessionVerifier(issuer='http://void.example',audience='void-music-api',public_key_pem=self.pem)
        with self.assertRaises(ValueError):
            ClerkSessionVerifier(issuer=self.issuer,audience='',public_key_pem=self.pem)
