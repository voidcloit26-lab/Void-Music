"""VOID Access transaction core. Not an HTTP service or production auth layer.

Only a trusted server adapter may call these functions with verified identities
and a verified device public-key fingerprint. No owner credentials in the APK.
SQLite is for isolated development; production TiDB needs equivalent row locks.
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS invitations (
    digest BLOB PRIMARY KEY, remaining INTEGER NOT NULL CHECK(remaining > 0),
    expires_at INTEGER
);
CREATE TABLE IF NOT EXISTS activations (
    account_id TEXT PRIMARY KEY, device_fingerprint TEXT UNIQUE NOT NULL,
    activated_at INTEGER NOT NULL, revoked_at INTEGER
);
"""
CODE_RE = re.compile(r"VOID-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}")
FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
ACCOUNT_RE = re.compile(r"[1-9][0-9]{15,20}")

class AccessDenied(Exception):
    pass

class AccessStore:
    def __init__(self, database: str, pepper: bytes):
        if len(pepper) < 32:
            raise ValueError("server-side pepper must be at least 32 bytes")
        self.database = database
        self.pepper = pepper
        with self._transaction() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _digest(self, code):
        return hmac.digest(self.pepper, code.encode("ascii"), hashlib.sha256)

    @staticmethod
    def _cleanup(db, now):
        return db.execute("DELETE FROM invitations WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)).rowcount

    def cleanup(self):
        with self._transaction() as db:
            return self._cleanup(db, int(time.time()))

    def generate(self, uses=1, ttl_seconds=86400):
        if type(uses) is not int or not 1 <= uses <= 1000:
            raise ValueError("uses must be 1..1000")
        if ttl_seconds is not None and (type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 31_536_000):
            raise ValueError("invalid redemption expiry")
        now = int(time.time())
        raw = secrets.token_hex(16).upper()
        code = "VOID-" + "-".join(raw[i:i+8] for i in range(0, 32, 8))
        with self._transaction() as db:
            self._cleanup(db, now)
            db.execute("INSERT INTO invitations VALUES (?, ?, ?)",
                       (self._digest(code), uses, None if ttl_seconds is None else now + ttl_seconds))
        return code

    def redeem(self, code, account_id, device_fingerprint):
        if not isinstance(account_id, str) or not ACCOUNT_RE.fullmatch(account_id):
            raise AccessDenied("invalid identity")
        if not isinstance(device_fingerprint, str) or not FINGERPRINT_RE.fullmatch(device_fingerprint):
            raise AccessDenied("invalid device")
        if not isinstance(code, str) or len(code) > 64:
            raise AccessDenied("invalid invitation")
        code = code.strip().upper()
        if not CODE_RE.fullmatch(code):
            raise AccessDenied("invalid invitation")
        now = int(time.time())
        with self._transaction() as db:
            self._cleanup(db, now)
            existing = db.execute("SELECT device_fingerprint, revoked_at FROM activations WHERE account_id=?", (account_id,)).fetchone()
            if existing:
                if existing[1] is None and hmac.compare_digest(existing[0], device_fingerprint):
                    return "already_active"
                raise AccessDenied("owner approval required")
            if db.execute("SELECT 1 FROM activations WHERE device_fingerprint=?", (device_fingerprint,)).fetchone():
                raise AccessDenied("device already assigned")
            digest = self._digest(code)
            row = db.execute("SELECT remaining FROM invitations WHERE digest=?", (digest,)).fetchone()
            if not row:
                raise AccessDenied("invalid or unavailable invitation")
            db.execute("INSERT INTO activations VALUES (?, ?, ?, NULL)", (account_id, device_fingerprint, now))
            if row[0] == 1:
                db.execute("DELETE FROM invitations WHERE digest=?", (digest,))
            else:
                db.execute("UPDATE invitations SET remaining=remaining-1 WHERE digest=?", (digest,))
            return "activated"

    def revoke(self, account_id):
        with self._transaction() as db:
            return db.execute("UPDATE activations SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                              (int(time.time()), account_id)).rowcount == 1

    def is_active(self, account_id, device_fingerprint):
        with self._transaction() as db:
            row = db.execute("SELECT 1 FROM activations WHERE account_id=? AND device_fingerprint=? AND revoked_at IS NULL",
                             (account_id, device_fingerprint)).fetchone()
            return row is not None

    def cancel(self, code):
        if not isinstance(code, str) or len(code) > 64 or not CODE_RE.fullmatch(code.strip().upper()):
            return False
        with self._transaction() as db:
            return db.execute("DELETE FROM invitations WHERE digest=?", (self._digest(code.strip().upper()),)).rowcount == 1
