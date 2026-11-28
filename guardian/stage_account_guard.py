"""Staging pre-authentication guard; process-local account fairness.

The downstream protocol must still verify the token and device proof. This
guard is not a replacement for the shared global budget or edge rate limits.
"""
import hashlib
import hmac
import threading
import time

from guardian.clerk_session import SessionDenied


class AccountFairness:
    def __init__(self, *, limit=12, capacity=512, clock=time.monotonic):
        if type(limit) is not int or type(capacity) is not int or limit < 1 or capacity < 1:
            raise ValueError("invalid limiter capacity")
        self.limit, self.capacity, self.clock = limit, capacity, clock
        self.lock = threading.Lock()
        self.entries = {}

    def take(self, identity):
        with self.lock:
            now = self.clock()
            self.entries = {k: v for k, v in self.entries.items() if now < v[0] + 60}
            row = self.entries.get(identity)
            if row is None:
                if len(self.entries) >= self.capacity:
                    return False
                self.entries[identity] = (now, 1)
                return True
            if now < row[0] or row[1] >= self.limit:
                return False
            self.entries[identity] = (row[0], row[1] + 1)
            return True


class SharedAccountFairness:
    """Bounded per-identity quotas across workers; no raw subjects stored."""
    def __init__(self, store, *, limit=60, capacity=2048, clock=time.time, scope='account'):
        if type(limit) is not int or not 1 <= limit <= 120:
            raise ValueError("invalid identity quota")
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise ValueError("invalid identity capacity")
        if scope not in ("account", "release-download"):
            raise ValueError("invalid identity quota scope")
        self.scope = scope
        self.store, self.limit, self.capacity, self.clock = store, limit, capacity, clock
        with store.transaction() as db:
            db.execute("SELECT identity,window_start,used FROM identity_budget_v2 LIMIT 0")

    def take(self, identity):
        issuer, subject = identity
        domain = "account-quota-v2:" if self.scope == "account" else "release-download-quota-v2:"
        digest = hmac.new(self.store.pepper, (domain+issuer+":"+subject).encode("ascii"),
                          hashlib.sha256).hexdigest()
        with self.store.transaction() as db:
            now = int(self.clock())
            if now <= 0:
                return False
            db.execute("DELETE FROM identity_budget_v2 WHERE window_start<=?", (now-60,))
            row = db.execute("SELECT window_start,used FROM identity_budget_v2 WHERE identity=?", (digest,)).fetchone()
            if row is not None:
                if now < row[0] or row[1] >= self.limit:
                    return False
                db.execute("UPDATE identity_budget_v2 SET used=used+1 WHERE identity=?", (digest,))
                return True
            if db.execute("SELECT count(*) FROM identity_budget_v2").fetchone()[0] >= self.capacity:
                return False
            db.execute("INSERT INTO identity_budget_v2 VALUES (?,?,1)", (digest, now))
            return True


def authorize_request(env, verifier, fairness):
    auth = env.get("HTTP_AUTHORIZATION", "")
    if not isinstance(auth, str) or not auth.startswith("Bearer ") or not 7 < len(auth) <= 8199:
        return "401 Unauthorized", {"error": "invalid_session"}
    try:
        session = verifier.verify(auth[7:])
    except SessionDenied:
        return "401 Unauthorized", {"error": "invalid_session"}
    except Exception:
        return "503 Service Unavailable", {"error": "unavailable"}
    try:
        allowed = fairness.take((session.issuer, session.subject))
    except Exception:
        return "503 Service Unavailable", {"error": "unavailable"}
    if not allowed:
        return "429 Too Many Requests", {"error": "retry_later"}
    return None
