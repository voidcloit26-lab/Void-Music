"""Isolated verifier for a configured Clerk session JWT policy.
No live routes, network key discovery, owner privileges or device authorization.
The deployment must provision a trusted RSA public key and dedicated audience.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class SessionDenied(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedSession:
    issuer: str
    subject: str
    session_id: str
    factor_age: tuple | None = None
    issued_at: int | None = None


class ClerkSessionVerifier:
    def __init__(self, *, issuer, audience, public_key_pem, authorized_parties=()):
        url = urlsplit(issuer)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.port or url.path or url.query or url.fragment:
            raise ValueError('exact HTTPS issuer required')
        if not isinstance(audience, str) or not audience or len(audience) > 128:
            raise ValueError('dedicated audience required')
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
            raise ValueError('trusted RSA public key required')
        self.issuer, self.audience, self.key = issuer, audience, key
        self.parties = frozenset(authorized_parties)

    def verify(self, token):
        if not isinstance(token, str) or not 1 <= len(token) <= 8192 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token):
            raise SessionDenied('invalid session')
        try:
            claims = jwt.decode(token, self.key, algorithms=['RS256'], issuer=self.issuer,
                                audience=self.audience, leeway=5,
                                options={'require': ['iss','aud','sub','sid','exp','nbf','iat'], 'strict_aud': True})
            if any(type(claims[k]) is not int for k in ('exp','nbf','iat')):
                raise ValueError('invalid timestamps')
            if not 0 < claims['exp']-claims['iat'] <= 300 or claims['nbf'] > claims['exp']:
                raise ValueError('invalid lifetime')
            if not re.fullmatch(r'user_[A-Za-z0-9]{1,120}', claims['sub']):
                raise ValueError('invalid subject')
            if not re.fullmatch(r'sess_[A-Za-z0-9]{1,120}', claims['sid']):
                raise ValueError('invalid session id')
            if claims.get('sts', 'active') != 'active' or 'act' in claims:
                raise ValueError('pending or impersonated session')
            # Native clients may lack azp. A present origin must be allowlisted.
            if 'azp' in claims and claims['azp'] not in self.parties:
                raise ValueError('unauthorized party')
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise SessionDenied('invalid session') from exc
        fva = claims.get('fva')
        if fva is not None:
            if (not isinstance(fva,list) or len(fva)!=2 or
                    any(type(x) is not int or not -1 <= x <= 1000000000 for x in fva)):
                raise SessionDenied('invalid factor age')
            return VerifiedSession(self.issuer,claims['sub'],claims['sid'],tuple(fva),claims['iat'])
        return VerifiedSession(self.issuer, claims['sub'], claims['sid'])
