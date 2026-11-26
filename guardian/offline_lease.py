"""Isolated signed offline entitlement; no production or Android wiring.
Caller must persist trusted clock evidence and enforce device key possession.
"""
from dataclasses import asdict, dataclass
import json
import re
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

MAX_SECONDS = 86400
AUDIENCE = 'online.voidbot.music'

@dataclass(frozen=True)
class Lease:
    account: str
    device: str
    issued_at: int
    expires_at: int
    membership_expires_at: int | None
    audience: str = AUDIENCE
    version: int = 2

    def validate(self):
        if self.audience != AUDIENCE or type(self.version) is not int or self.version != 2:
            raise ValueError('wrong lease target')
        if not re.fullmatch(r'[0-9a-f]{32}', self.account) or not re.fullmatch(r'[0-9a-f]{64}', self.device):
            raise ValueError('invalid binding')
        if type(self.issued_at) is not int or type(self.expires_at) is not int or not 0 < self.issued_at < self.expires_at <= self.issued_at + MAX_SECONDS:
            raise ValueError('invalid duration')
        if self.membership_expires_at is not None and (type(self.membership_expires_at) is not int or self.expires_at > self.membership_expires_at):
            raise ValueError('lease exceeds membership')
        return self

    def canonical(self):
        return json.dumps(asdict(self),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def issue(member, account, device, now, key):
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('P-256 signing key required')
    lease = Lease(account,device,now,member.lease_until(now),member.expires_at).validate()
    payload = lease.canonical()
    return payload,key.sign(payload,ec.ECDSA(hashes.SHA256()))


def verify(payload, signature, key, *, account, device, now, trusted_floor):
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('P-256 verification key required')
    if not isinstance(payload,bytes) or not 0<len(payload)<=2048 or not isinstance(signature,bytes) or not 0<len(signature)<=80:
        raise ValueError('invalid lease size')
    key.verify(signature,payload,ec.ECDSA(hashes.SHA256()))
    lease=Lease(**json.loads(payload.decode('ascii'))).validate()
    if lease.canonical()!=payload or lease.account!=account or lease.device!=device:
        raise ValueError('lease binding mismatch')
    if type(now) is not int or type(trusted_floor) is not int or not 0<trusted_floor<=now:
        raise ValueError('clock rollback or missing trusted time')
    if not lease.issued_at<=now<lease.expires_at or lease.issued_at<trusted_floor-MAX_SECONDS:
        raise ValueError('expired or stale lease')
    return lease
