"""Staging pre-authentication guard; process-local account fairness.

The downstream protocol must still verify the token and device proof. This
guard is not a replacement for the shared global budget or edge rate limits.
"""
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
    if not fairness.take((session.issuer, session.subject)):
        return "429 Too Many Requests", {"error": "retry_later"}
    return None
