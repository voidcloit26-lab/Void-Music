"""Sandbox-only manual payment ledger. No real-chain verification or HTTP API.

Requires trusted owner calls and verified device proofs. Live payment issuance
must remain disabled until a production adapter and legal gates are approved.
"""
from contextlib import closing
import re
import secrets
import sqlite3
from guardian.identity_store import IdentityStore
from guardian.membership_rules import MembershipDenied, grant

LEDGER = """
CREATE TABLE IF NOT EXISTS test_payments_v2 (
    id TEXT PRIMARY KEY,
    account TEXT NOT NULL REFERENCES accounts_v2(id),
    reference TEXT NOT NULL UNIQUE,
    usd_cents INTEGER NOT NULL CHECK(usd_cents > 0),
    recorded_at INTEGER NOT NULL,
    voided_at INTEGER,
    consumed_at INTEGER
);
CREATE TABLE IF NOT EXISTS test_paid_keys_v2 (
    payment TEXT PRIMARY KEY REFERENCES test_payments_v2(id),
    digest BLOB NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('annual','renewal')),
    expires_at INTEGER NOT NULL
);
"""

class SandboxLedger(IdentityStore):
    def __init__(self, path, pepper, *, sandbox=False, price_cents=500, **kwargs):
        if sandbox is not True:
            raise PermissionError("sandbox only")
        if type(price_cents) is not int or not 1 <= price_cents <= 1000000:
            raise ValueError("invalid USD price")
        self.price_cents = price_cents
        super().__init__(path, pepper, **kwargs)
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.executescript(LEDGER)

    def record_test_payment(self, account, reference, usd_cents):
        """Synthetic receipt only: never interprets a real transaction as paid."""
        account = self._account(account)
        if not isinstance(reference, str) or not re.fullmatch(r"test:[0-9a-f]{64}", reference):
            raise ValueError("synthetic reference required")
        if type(usd_cents) is not int or usd_cents != self.price_cents:
            raise MembershipDenied("quoted price mismatch")
        with self.transaction() as db:
            row = db.execute("SELECT id,account,usd_cents FROM test_payments_v2 WHERE reference=?", (reference,)).fetchone()
            if row:
                if row[1:] != (account, usd_cents):
                    raise MembershipDenied("receipt already assigned")
                return row[0]
            if not db.execute("SELECT 1 FROM accounts_v2 WHERE id=?", (account,)).fetchone():
                raise MembershipDenied("unknown account")
            payment = secrets.token_hex(16)
            db.execute("INSERT INTO test_payments_v2 VALUES (?,?,?,?,?,NULL,NULL)",
                       (payment, account, reference, usd_cents, self._now()))
            return payment

    def issue_paid_test_key(self, payment, *, ttl=86400):
        payment = self._account(payment)
        if type(ttl) is not int or not 1 <= ttl <= 604800:
            raise ValueError("invalid key expiry")
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            now = self._now()
            row = db.execute("SELECT account,voided_at,consumed_at FROM test_payments_v2 WHERE id=?", (payment,)).fetchone()
            if not row or row[1] is not None or row[2] is not None:
                raise MembershipDenied("receipt unavailable")
            account = row[0]
            membership = self._membership(db, account)
            kind = "renewal" if membership is not None else "annual"
            grant(membership, kind, now)
            # Reissue only after previous key expiry; no overlapping keys.
            prior = db.execute("SELECT expires_at FROM test_paid_keys_v2 WHERE payment=?", (payment,)).fetchone()
            if prior and prior[0] > now:
                raise MembershipDenied("key already issued")
            db.execute("INSERT INTO test_paid_keys_v2 VALUES (?,?,?,?) ON CONFLICT(payment) DO UPDATE SET digest=excluded.digest,kind=excluded.kind,expires_at=excluded.expires_at",
                       (payment,self._digest("paid-test",token),kind,now+ttl))
        return token

    def redeem_paid_test(self, account, verified_device, token):
        account, device = self._account(account), self._device(verified_device)
        digest = self._digest("paid-test", token)
        with self.transaction() as db:
            now = self._now()
            self._require_device(db, account, device)
            row = db.execute("SELECT p.id,k.kind,k.expires_at,p.voided_at,p.consumed_at FROM test_paid_keys_v2 k JOIN test_payments_v2 p ON p.id=k.payment WHERE k.digest=? AND p.account=?",
                             (digest,account)).fetchone()
            if not row or row[2] <= now or row[3] is not None or row[4] is not None:
                raise MembershipDenied("key unavailable")
            result = grant(self._membership(db, account), row[1], now)
            db.execute("INSERT INTO memberships_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET kind=excluded.kind,expires_at=excluded.expires_at,state=excluded.state",
                       (account,result.kind,result.expires_at,result.state))
            db.execute("UPDATE test_payments_v2 SET consumed_at=? WHERE id=?", (now,row[0]))
            return result

    def void_unredeemed(self, payment):
        """Administrative record only; does not send or refund cryptocurrency."""
        with self.transaction() as db:
            return db.execute("UPDATE test_payments_v2 SET voided_at=? WHERE id=? AND voided_at IS NULL AND consumed_at IS NULL",
                              (self._now(),self._account(payment))).rowcount == 1
