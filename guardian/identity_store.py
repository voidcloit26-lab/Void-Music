"""Isolated SQLite identity and membership transaction prototype.

Trusted callers must first authenticate owners and prove device key possession.
Not an HTTP API or production store. Paid mode is deliberately absent.
"""
from contextlib import contextmanager
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from guardian.membership_rules import Membership, MembershipDenied, grant

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts_v2 (
    id TEXT PRIMARY KEY, device TEXT UNIQUE NOT NULL,
    recovery BLOB UNIQUE NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships_v2 (
    account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
    kind TEXT NOT NULL, expires_at INTEGER, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations_v2 (
    digest BLOB PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts_v2(id),
    kind TEXT NOT NULL, days INTEGER, expires_at INTEGER NOT NULL,
    redeemed_at INTEGER
);
"""
HEX = re.compile(r"[0-9a-f]{64}")
ACCOUNT = re.compile(r"[0-9a-f]{32}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")

class IdentityStore:
    def __init__(self, path, pepper, *, clock=time.time):
        if not isinstance(pepper, bytes) or len(pepper) < 32:
            raise ValueError("server secret required")
        self.path, self.pepper, self.clock = path, pepper, clock
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _now(self):
        return int(self.clock())

    def _digest(self, domain, token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise MembershipDenied("invalid credential")
        return hmac.digest(self.pepper, (domain + ":" + token).encode("ascii"), hashlib.sha256)

    @staticmethod
    def _device(value):
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise MembershipDenied("invalid device")
        return value

    @staticmethod
    def _account(value):
        if not isinstance(value, str) or not ACCOUNT.fullmatch(value):
            raise MembershipDenied("invalid account")
        return value

    def create_account(self, verified_device):
        """Requires verified key possession and admission by trusted caller."""
        device = self._device(verified_device)
        account, recovery = secrets.token_hex(16), secrets.token_urlsafe(32)
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=?", (device,)).fetchone():
                raise MembershipDenied("device already assigned")
            db.execute("INSERT INTO accounts_v2 VALUES (?,?,?,?)",
                       (account, device, self._digest("recovery", recovery), self._now()))
        return account, recovery

    def recover(self, account, recovery, verified_new_device):
        account, device = self._account(account), self._device(verified_new_device)
        digest = self._digest("recovery", recovery)
        replacement = secrets.token_urlsafe(32)
        with self.transaction() as db:
            row = db.execute("SELECT recovery FROM accounts_v2 WHERE id=?", (account,)).fetchone()
            if row is None or not hmac.compare_digest(row[0], digest):
                raise MembershipDenied("recovery denied")
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=? AND id<>?", (device, account)).fetchone():
                raise MembershipDenied("device already assigned")
            db.execute("UPDATE accounts_v2 SET device=?, recovery=? WHERE id=?",
                       (device, self._digest("recovery", replacement), account))
        return replacement

    @staticmethod
    def _membership(db, account):
        row = db.execute("SELECT kind,expires_at,state FROM memberships_v2 WHERE account=?",
                         (account,)).fetchone()
        return Membership(*row) if row else None

    @staticmethod
    def _require_device(db, account, device):
        if not db.execute("SELECT 1 FROM accounts_v2 WHERE id=? AND device=?",
                          (account, device)).fetchone():
            raise MembershipDenied("device not authorized")

    def membership(self, account, verified_device):
        with self.transaction() as db:
            self._require_device(db, self._account(account), self._device(verified_device))
            return self._membership(db, account)

    def issue_free(self, account, kind, *, days=None, ttl=86400):
        """Owner-only adapter required. Paid issuance is not implemented."""
        account = self._account(account)
        if kind not in ("lifetime", "trial", "complimentary"):
            raise MembershipDenied("paid issuance disabled")
        if type(ttl) is not int or not 1 <= ttl <= 604800:
            raise ValueError("invalid invitation lifetime")
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            now = self._now()
            if not db.execute("SELECT 1 FROM accounts_v2 WHERE id=?", (account,)).fetchone():
                raise MembershipDenied("unknown account")
            grant(self._membership(db, account), kind, now, days=days)
            db.execute("INSERT INTO invitations_v2 VALUES (?,?,?,?,?,NULL)",
                       (self._digest("invite", token), account, kind, days, now+ttl))
        return token

    def redeem(self, account, verified_device, token):
        account, device = self._account(account), self._device(verified_device)
        digest = self._digest("invite", token)
        with self.transaction() as db:
            now = self._now()
            self._require_device(db, account, device)
            row = db.execute("SELECT kind,days,expires_at,redeemed_at FROM invitations_v2 WHERE digest=? AND account=?",
                             (digest, account)).fetchone()
            if not row or row[2] <= now or row[3] is not None:
                raise MembershipDenied("invitation unavailable")
            result = grant(self._membership(db, account), row[0], now, days=row[1])
            db.execute("INSERT INTO memberships_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET kind=excluded.kind,expires_at=excluded.expires_at,state=excluded.state",
                       (account, result.kind, result.expires_at, result.state))
            db.execute("UPDATE invitations_v2 SET redeemed_at=? WHERE digest=?", (now, digest))
            return result

    def set_state(self, account, state):
        """Owner-only adapter required; no implicit reinstatement by redemption."""
        if state not in ("suspended", "revoked"):
            raise ValueError("explicit reinstatement workflow not implemented")
        with self.transaction() as db:
            return db.execute("UPDATE memberships_v2 SET state=? WHERE account=?",
                              (state, self._account(account))).rowcount == 1
