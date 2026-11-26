"""Durable, bounded native owner session; never stores raw tokens.

Requires a separately provisioned table. The existing activation database
transaction lock serializes replacement, expiry, and revocation.
"""
import hashlib
import hmac
import re
import time

NATIVE_SESSION_SECONDS = 12 * 60 * 60

class NativeOwnerSessions:
    def __init__(self, store, scope: bytes, clock=time.time):
        if len(scope) != 32:
            raise ValueError("invalid owner session scope")
        self.store, self.scope, self.clock = store, scope, clock
        # Fail closed when the migration is missing. Runtime never creates tables.
        with self.store._transaction() as db:
            db.execute("SELECT digest, expires_at FROM native_owner_session LIMIT 0")

    def digest(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ValueError("invalid owner session token")
        return hmac.digest(self.scope, b"VOID-native-owner-session-v1:" + token.encode("ascii"), hashlib.sha256)

    def replace(self, token):
        digest = self.digest(token)
        with self.store._transaction() as db:
            db.execute("DELETE FROM native_owner_session")
            db.execute("INSERT INTO native_owner_session(slot, digest, expires_at) VALUES (1, ?, ?)",
                       (digest, int(self.clock()) + NATIVE_SESSION_SECONDS))

    def valid(self, token):
        digest = self.digest(token)
        with self.store._transaction() as db:
            now = int(self.clock())
            db.execute("DELETE FROM native_owner_session WHERE expires_at <= ?", (now,))
            row = db.execute("SELECT digest FROM native_owner_session WHERE slot=1").fetchone()
            return row is not None and hmac.compare_digest(bytes(row[0]), digest)

    def revoke(self, token):
        digest = self.digest(token)
        with self.store._transaction() as db:
            db.execute("DELETE FROM native_owner_session WHERE slot=1 AND digest=?", (digest,))

    def clear(self):
        with self.store._transaction() as db:
            db.execute("DELETE FROM native_owner_session")
