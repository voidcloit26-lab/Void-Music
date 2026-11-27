"""Independent short-lived V2 owner credentials, not Clerk customer tokens."""
import hashlib
import hmac
import re
import secrets
import time

from guardian.business_store import BusinessDenied

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
SESSION_SECONDS = 300


class BusinessSessions:
    def __init__(self, store, *, owner_id, salt, digest, scope, clock=time.time):
        if not isinstance(owner_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", owner_id):
            raise ValueError("invalid owner")
        if any(not isinstance(v, bytes) or len(v) != 32 for v in (salt, digest, scope)):
            raise ValueError("invalid owner credential configuration")
        self.store, self.owner_id, self.salt, self.digest, self.scope = store, owner_id, salt, digest, scope
        self.clock = clock
        with store.transaction() as db:
            db.execute("SELECT digest,issued_at,expires_at FROM business_session_v2 LIMIT 0")
            db.execute("SELECT window_start,used FROM business_login_budget_v2 LIMIT 0")

    @staticmethod
    def password_hash(password, salt):
        if not isinstance(password, str) or not 16 <= len(password) <= 256:
            raise ValueError("invalid owner password")
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1,
                              dklen=32, maxmem=256*1024*1024)

    def _digest(self, token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise BusinessDenied("invalid owner credential")
        return hmac.digest(self.scope, b"VOID-business-v2:" + token.encode("ascii"), "sha256")

    def _budget(self):
        with self.store.transaction() as db:
            now = int(self.clock())
            if now <= 0:
                return False
            row = db.execute("SELECT window_start,used FROM business_login_budget_v2 WHERE singleton=1").fetchone()
            if not row or now >= row[0]+60:
                db.execute("INSERT INTO business_login_budget_v2 VALUES (1,?,1) ON CONFLICT(singleton) DO UPDATE SET window_start=excluded.window_start,used=1", (now,))
                return True
            if now < row[0] or row[1] >= 3:
                return False
            db.execute("UPDATE business_login_budget_v2 SET used=used+1 WHERE singleton=1")
            return True

    def login(self, owner, password):
        if not isinstance(owner,str) or not 1 <= len(owner) <= 128 or not isinstance(password,str) or not 16 <= len(password) <= 256:
            raise BusinessDenied("invalid owner credentials")
        if not self._budget():
            raise BusinessDenied("owner login unavailable")
        candidate = self.password_hash(password, self.salt)
        if not (hmac.compare_digest(candidate,self.digest) and
                hmac.compare_digest(owner.encode("utf-8"),self.owner_id.encode("utf-8"))):
            raise BusinessDenied("invalid owner credentials")
        token = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            now = int(self.clock())
            if now <= 0:
                raise BusinessDenied("owner login unavailable")
            db.execute("INSERT INTO business_session_v2 VALUES (1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET digest=excluded.digest,issued_at=excluded.issued_at,expires_at=excluded.expires_at",
                       (self._digest(token),now,now+SESSION_SECONDS))
        return token

    def verify(self, token):
        digest = self._digest(token)
        with self.store.transaction() as db:
            row = db.execute("SELECT digest,issued_at,expires_at FROM business_session_v2 WHERE singleton=1").fetchone()
            now = int(self.clock())
            if not row or not 0 < row[1] <= now < row[2] or row[2]-row[1] != SESSION_SECONDS or not hmac.compare_digest(bytes(row[0]),digest):
                raise BusinessDenied("owner session invalid")
            return self.owner_id, row[1]

    def logout(self, token):
        digest = self._digest(token)
        with self.store.transaction() as db:
            # Do not revoke a different owner's replacement session.
            return bool(db.execute("DELETE FROM business_session_v2 WHERE singleton=1 AND digest=?", (digest,)).rowcount)
