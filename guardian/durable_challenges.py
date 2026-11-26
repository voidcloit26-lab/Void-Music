"""Shared, bounded, single-use proof challenges for Guardian V2.

Uses the supplied identity store's serialized transaction. Schema provisioning
is separate; never creates tables or grants privileges at runtime.
"""
import hashlib
import re
import secrets
import time

DDL = """CREATE TABLE IF NOT EXISTS proof_challenges_v2 (
    nonce TEXT PRIMARY KEY, scope TEXT NOT NULL, device TEXT NOT NULL,
    digest TEXT NOT NULL, expires_at BIGINT NOT NULL,
    UNIQUE(scope, device)
);"""
HEX = re.compile(r"[a-f0-9]{64}")
NONCE = re.compile(r"[A-Za-z0-9_-]{43}")

class ChallengeDenied(ValueError):
    pass

class DurableChallenges:
    def __init__(self, store, *, clock=time.time, max_pending=1024, per_scope=4):
        if type(max_pending) is not int or not 1 <= max_pending <= 10000:
            raise ValueError("invalid challenge capacity")
        if type(per_scope) is not int or not 1 <= per_scope <= 16:
            raise ValueError("invalid scope capacity")
        self.store, self.clock = store, clock
        self.max_pending, self.per_scope = max_pending, per_scope
        with store.transaction() as db:
            db.execute("SELECT nonce,scope,device,digest,expires_at FROM proof_challenges_v2 LIMIT 0")

    @staticmethod
    def scope(issuer, subject):
        return hashlib.sha256((issuer + "\n" + subject).encode("ascii")).hexdigest()

    @staticmethod
    def digest(proof):
        if not isinstance(proof, bytes) or not 1 <= len(proof) <= 2048:
            raise ValueError("invalid proof")
        return hashlib.sha256(proof).hexdigest()

    def issue(self, scope, device, proof_for_nonce):
        if not HEX.fullmatch(scope) or not HEX.fullmatch(device):
            raise ValueError("invalid binding")
        nonce = secrets.token_urlsafe(32)
        digest = self.digest(proof_for_nonce(nonce))
        with self.store.transaction() as db:
            now = int(self.clock())
            db.execute("DELETE FROM proof_challenges_v2 WHERE expires_at<=?", (now,))
            if db.execute("SELECT count(*) FROM proof_challenges_v2").fetchone()[0] >= self.max_pending:
                raise ChallengeDenied("challenge capacity reached")
            if db.execute("SELECT count(*) FROM proof_challenges_v2 WHERE scope=?", (scope,)).fetchone()[0] >= self.per_scope:
                raise ChallengeDenied("scope capacity reached")
            if db.execute("SELECT 1 FROM proof_challenges_v2 WHERE scope=? AND device=?", (scope,device)).fetchone():
                raise ChallengeDenied("challenge already pending")
            db.execute("INSERT INTO proof_challenges_v2 VALUES (?,?,?,?,?)", (nonce,scope,device,digest,now+60))
        return nonce

    def consume(self, nonce, scope, device, proof):
        if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
            raise ChallengeDenied("invalid challenge")
        digest = self.digest(proof)
        with self.store.transaction() as db:
            now = int(self.clock())
            # Conditional deletion is the single-use atomic operation. Signature
            # verification must happen before this call in the protocol adapter.
            result = db.execute("DELETE FROM proof_challenges_v2 WHERE nonce=? AND scope=? AND device=? AND digest=? AND expires_at>?",
                (nonce,scope,device,digest,now))
            if result.rowcount != 1:
                raise ChallengeDenied("invalid challenge")
