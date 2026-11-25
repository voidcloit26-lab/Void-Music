"""Guardian device-proof and signed entitlement core (no public HTTP listener).

Use behind a rate-limited TLS API. Device key possession is not device attestation
or proof of a Discord identity. A code grants one device slot; no Discord login
is required for activation. Signing keys remain exclusively on the server.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.access_store import AccessDenied, CODE_RE

AUDIENCE = "online.voidbot.music"
NONCE_RE = re.compile(r"[A-Za-z0-9_-]{43}")

def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def unb64(value, maximum=4096):
    if not isinstance(value, str) or not value or len(value) > maximum or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise AccessDenied("invalid encoding")
    try:
        result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError as exc:
        raise AccessDenied("invalid encoding") from exc
    if b64(result) != value:
        raise AccessDenied("noncanonical encoding")
    return result

def read_device_key(encoded):
    try:
        key = serialization.load_der_public_key(unb64(encoded, 256))
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise AccessDenied("P-256 device key required")
        canonical = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return key, hashlib.sha256(canonical).hexdigest()
    except (ValueError, TypeError) as exc:
        raise AccessDenied("invalid device key") from exc

def device_account(fingerprint):
    # Internal numeric device identifier, NOT a Discord user ID.
    # A collision is rejected by the store's exact fingerprint check.
    return str(10**19 + int(fingerprint, 16) % (9 * 10**19))

def proof_message(nonce, fingerprint, action, code=""):
    digest = hashlib.sha256(code.encode("ascii")).hexdigest()
    return ("VOID-DEVICE-PROOF-v1\n" + nonce + "\n" + fingerprint + "\n" + action + "\n" + digest).encode("ascii")

class DeviceProtocol:
    def __init__(self, store, signing_key, clock=time.monotonic, max_challenges=1024):
        if not isinstance(signing_key, ec.EllipticCurvePrivateKey) or not isinstance(signing_key.curve, ec.SECP256R1):
            raise ValueError("P-256 server signing key required")
        self.store = store
        self.signing_key = signing_key
        self.clock = clock
        self.max_challenges = max_challenges
        self.lock = threading.Lock()
        self.pending = {}

    def challenge(self, public_key, action):
        _, fingerprint = read_device_key(public_key)
        if action not in ("redeem", "status"):
            raise AccessDenied("invalid action")
        with self.lock:
            now = self.clock()
            self.pending = {n: data for n, data in self.pending.items() if data[2] > now}
            if len(self.pending) >= self.max_challenges:
                raise AccessDenied("try again later")
            if any(d[0] == fingerprint for d in self.pending.values()):
                raise AccessDenied("device challenge already pending")
            nonce = secrets.token_urlsafe(32)
            self.pending[nonce] = (fingerprint, action, now + 120)
        return {"nonce": nonce, "expires_in": 120}

    def _verify(self, public_key, nonce, signature, action, code):
        key, fingerprint = read_device_key(public_key)
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise AccessDenied("invalid challenge")
        with self.lock:
            pending = self.pending.pop(nonce, None)
        if not pending or pending[:2] != (fingerprint, action) or pending[2] <= self.clock():
            raise AccessDenied("invalid or expired challenge")
        try:
            key.verify(unb64(signature, 256), proof_message(nonce, fingerprint, action, code), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise AccessDenied("invalid device proof") from exc
        return fingerprint

    def redeem(self, public_key, nonce, signature, code):
        if not isinstance(code, str) or len(code) > 64:
            raise AccessDenied("invalid invitation")
        code = code.strip().upper()
        if not CODE_RE.fullmatch(code):
            raise AccessDenied("invalid invitation")
        device = self._verify(public_key, nonce, signature, "redeem", code)
        account = device_account(device)
        self.store.redeem(code, account, device)
        return self._entitlement(account, device)

    def status(self, public_key, nonce, signature):
        device = self._verify(public_key, nonce, signature, "status", "")
        account = device_account(device)
        if not self.store.is_active(account, device):
            raise AccessDenied("access not active")
        return self._entitlement(account, device)

    def _entitlement(self, account, device):
        # Lifetime access has no local expiry; revocation requires a successful
        # online status check. Never embed the signing private key in an APK.
        payload = json.dumps({"v": 1, "aud": AUDIENCE, "device": device,
                              "account": account, "iat": int(time.time())},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = self.signing_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return {"payload": b64(payload), "signature": b64(signature)}
