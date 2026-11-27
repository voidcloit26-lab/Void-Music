"""Isolated V2 account protocol. Not mounted on the live Guardian API.

A verified Clerk token alone does not authorize a device. Every operation
requires a single-use P-256 proof bound to its exact action, body and session.
Includes unactivated registration, linked recovery and account operations.
No owner or payment routes.
"""
from dataclasses import asdict
import hashlib
import json
import secrets
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from guardian.access_store import AccessDenied
from guardian.device_protocol import NONCE_RE, read_device_key, unb64, b64
from guardian.offline_lease import issue as issue_lease
from guardian.membership_rules import MembershipDenied
from guardian.external_identity_store import ExternalIdentityStore
from guardian.cloud_store import CloudStore
from guardian.durable_challenges import DurableChallenges, ChallengeDenied


class LinkedCloudStore(ExternalIdentityStore, CloudStore):
    """SQLite-only composition; one identity and cloud database."""


ACTIONS = {
    "register": set(),
    "register_with_code": {"code"},
    "redeem_activation": {"code"},
    "recover": {"recovery"},
    "rotate_recovery": set(),
    "lease": set(),
    "status": set(),
    "redeem_free": {"code"},
    "cloud_read": set(),
    "cloud_write": {"revision", "library"},
    "cloud_clear": {"revision"},
}
MAX_BODY = 600 * 1024


def canonical_body(action, body):
    if action not in ACTIONS or not isinstance(body, dict) or set(body) != ACTIONS[action]:
        raise ValueError("invalid action body")
    if "revision" in body and (type(body["revision"]) is not int or not 0 <= body["revision"] < 2**63-1):
        raise ValueError("invalid revision")
    if "recovery" in body and (not isinstance(body["recovery"], str) or len(body["recovery"]) != 43):
        raise ValueError("invalid recovery credential")
    if "code" in body and (not isinstance(body["code"], str) or len(body["code"]) != 43):
        raise ValueError("invalid key")
    data = json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(data) > MAX_BODY:
        raise ValueError("request too large")
    return data


def message(nonce, fingerprint, session_id, subject, action, body):
    digest = hashlib.sha256(canonical_body(action, body)).hexdigest()
    return ("VOID-ACCOUNT-PROOF-v2\n" + nonce + "\n" + fingerprint + "\n" +
            session_id + "\n" + subject + "\n" + action + "\n" + digest).encode("ascii")


class AccountProtocol:
    def __init__(self, store, verifier, *, clock=time.monotonic, max_pending=1024, lease_key=None, challenges=None, activation_codes=None):
        self.store, self.verifier, self.clock = store, verifier, clock
        self.lease_key = lease_key
        self.challenges = challenges
        self.activation_codes = activation_codes
        self.max_pending = max_pending
        self.pending = {}
        self.lock = threading.Lock()

    def challenge(self, token, public_key, action, body):
        session = self.verifier.verify(token)
        _, fingerprint = read_device_key(public_key)
        canonical_body(action, body)
        # Except for registration and recovery, only the current linked device may allocate challenges.
        if action in ("register_with_code", "redeem_activation") and self.activation_codes is None:
            raise MembershipDenied("activation upgrade disabled")
        if action not in ("register", "recover", "register_with_code"):
            self.store.resolve(session.issuer, session.subject, fingerprint)
        if self.challenges is not None:
            scope = DurableChallenges.scope(session.issuer, session.subject)
            try:
                nonce = self.challenges.issue(scope, fingerprint, lambda n: message(
                    n, fingerprint, session.session_id, session.subject, action, body))
            except ChallengeDenied as exc:
                raise AccessDenied("challenge unavailable") from exc
            return {"nonce": nonce, "expires_in": 60}
        nonce = secrets.token_urlsafe(32)
        signed = message(nonce, fingerprint, session.session_id, session.subject, action, body)
        with self.lock:
            now = self.clock()
            self.pending = {n: p for n, p in self.pending.items() if p[1] > now}
            if len(self.pending) >= self.max_pending:
                raise AccessDenied("try again later")
            if any(p[2] == fingerprint for p in self.pending.values()):
                raise AccessDenied("challenge already pending")
            self.pending[nonce] = (signed, now+60, fingerprint)
        return {"nonce": nonce, "expires_in": 60}

    def execute(self, token, public_key, nonce, signature, action, body):
        session = self.verifier.verify(token)
        key, fingerprint = read_device_key(public_key)
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise AccessDenied("invalid nonce")
        signed = message(nonce, fingerprint, session.session_id, session.subject, action, body)
        if self.challenges is None:
            with self.lock:
                pending = self.pending.get(nonce)
            if not pending or pending[0] != signed or pending[1] <= self.clock():
                raise AccessDenied("invalid challenge")
        try:
            key.verify(unb64(signature, 256), signed, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise AccessDenied("invalid device proof") from exc
        if self.challenges is not None:
            try:
                self.challenges.consume(nonce, DurableChallenges.scope(session.issuer, session.subject), fingerprint, signed)
            except ChallengeDenied as exc:
                raise AccessDenied("invalid challenge") from exc
        else:
            with self.lock:
                if self.pending.get(nonce) != pending or pending[1] <= self.clock():
                    raise AccessDenied("invalid challenge")
                del self.pending[nonce]
        if action == "register_with_code":
            if self.activation_codes is None:
                raise MembershipDenied("activation upgrade disabled")
            account, recovery, member = self.activation_codes.register(session.issuer, session.subject, fingerprint, body["code"])
            return {"account":account,"recovery":recovery,"membership":asdict(member),"status":member.status(self.store._now())}
        if action == "redeem_activation":
            if self.activation_codes is None:
                raise MembershipDenied("activation upgrade disabled")
            member = self.activation_codes.redeem(session.issuer,session.subject,fingerprint,body["code"])
            return {"membership":asdict(member)}
        if action == "register":
            account, recovery = self.store.register(session.issuer, session.subject, fingerprint)
            return {"account": account, "recovery": recovery, "status": "unactivated"}
        if action == "recover":
            account, recovery = self.store.recover_linked(session.issuer, session.subject, body["recovery"], fingerprint)
            return {"account": account, "recovery": recovery}
        # Resolve again after proof; store operations recheck registered device
        # in their own transaction, so a concurrent recovery cannot reuse it.
        account = self.store.resolve(session.issuer, session.subject, fingerprint)
        if action == "rotate_recovery":
            return {"recovery": self.store.rotate_linked_recovery(session.issuer, session.subject, fingerprint)}
        if action == "lease":
            if self.lease_key is None:
                raise MembershipDenied("lease issuance disabled")
            member = self.store.membership(account, fingerprint)
            if member is None:
                raise MembershipDenied("inactive")
            payload, signature = issue_lease(member, account, fingerprint, self.store._now(), self.lease_key)
            return {"payload": b64(payload), "signature": b64(signature)}
        if action == "status":
            member = self.store.membership(account, fingerprint)
            return {"account": account, "membership": asdict(member) if member else None,
                    "status": member.status(self.store._now()) if member else "unactivated"}
        if action == "redeem_free":
            result = self.store.redeem(account, fingerprint, body["code"])
            return {"membership": asdict(result)}
        if action == "cloud_read":
            revision, library = self.store.read_library(account, fingerprint)
            return {"revision": revision, "library": library}
        if action == "cloud_write":
            return {"revision": self.store.write_library(account, fingerprint, body["revision"], body["library"])}
        if action == "cloud_clear":
            return {"revision": self.store.clear_library(account, fingerprint, body["revision"])}
        raise MembershipDenied("action unavailable")
