"""VOID Update policy primitives. Not wired to live services or Android yet.

The release signer is separate from Guardian entitlements and APK signing.
Only a verified manifest may establish a mandatory update.
"""
from dataclasses import asdict, dataclass
import json
import re
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

PACKAGE = "online.voidbot.music"
MAX_TTL = 7 * 24 * 60 * 60
MAX_APK_BYTES = 500 * 1024 * 1024

@dataclass(frozen=True)
class ReleasePolicy:
    sequence: int
    latest: int
    minimum: int
    version_name: str
    apk_sha256: str
    signer_sha256: str
    apk_bytes: int
    issued_at: int
    expires_at: int
    package: str = PACKAGE
    channel: str = "stable"

    def validate(self, now):
        ints = (self.sequence, self.latest, self.minimum, self.apk_bytes,
                self.issued_at, self.expires_at)
        if any(type(n) is not int for n in ints):
            raise ValueError("invalid numeric policy field")
        if not (0 < self.sequence <= 2**63-1 and
                0 < self.minimum <= self.latest <= 2100000000):
            raise ValueError("invalid versions")
        if self.package != PACKAGE or self.channel != "stable":
            raise ValueError("wrong release target")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version_name):
            raise ValueError("invalid version name")
        for value in (self.apk_sha256, self.signer_sha256):
            if not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError("invalid digest")
        if not 0 < self.apk_bytes <= MAX_APK_BYTES:
            raise ValueError("invalid APK size")
        if not (0 < self.issued_at <= now + 300 and
                now < self.expires_at <= self.issued_at + MAX_TTL):
            raise ValueError("expired or invalid policy lifetime")
        return self

    def canonical(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii")

    def decision(self, installed):
        if type(installed) is not int or installed <= 0:
            raise ValueError("invalid installed version")
        if installed < self.minimum:
            return "required"
        if installed < self.latest:
            return "available"
        return "current"

def verify_policy(payload, signature, public_key, now, previous=None):
    """Verify signature and strict canonical encoding; reject replay/sequence reuse.

    Caller must persist the last accepted policy atomically across launches.
    A policy outage must not be interpreted as proof of a mandatory update.
    """
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 4096:
        raise ValueError("invalid policy size")
    if not isinstance(signature, bytes) or not 0 < len(signature) <= 80:
        raise ValueError("invalid signature size")
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
        raise ValueError("wrong release verification key")
    public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    candidate = ReleasePolicy(**json.loads(payload.decode("ascii"))).validate(now)
    if candidate.canonical() != payload:
        raise ValueError("noncanonical policy")
    if previous is not None:
        if candidate.sequence < previous.sequence:
            raise ValueError("stale policy")
        if candidate.sequence == previous.sequence and candidate != previous:
            raise ValueError("sequence reuse")
    return candidate
