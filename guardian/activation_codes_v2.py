"""Account-first activation. No payment processing or device-owned membership.

Requires authenticated external identity and device proof before calling customer
methods, and an independently verified owner before calling administrative methods.
A registration, code redemption and membership grant share one transaction.
"""
import secrets
import hmac
import hashlib
import re
from guardian.membership_rules import MembershipDenied, grant
from guardian.business_store import BusinessDenied

DDL = """CREATE TABLE IF NOT EXISTS activation_codes_v2 (
 digest BYTEA PRIMARY KEY, kind TEXT NOT NULL,
 days INTEGER, expires_at BIGINT, bound_identity BYTEA,
 redeemed_account TEXT REFERENCES accounts_v2(id), redeemed_at BIGINT,
 cancelled_at BIGINT
);"""


class ActivationCodes:
    def __init__(self, store, *, issuer=None, collective=False):
        self.store = store
        self.issuer = issuer or getattr(store, 'issuer', None)
        self.collective = collective is True

    def issue(self, credential, kind, *, days=None, ttl=604800, subject=None, count=1, claim_limit=1):
        actor = self.store._owner(credential)
        if kind not in ("annual","renewal","lifetime","trial","complimentary"):
            raise BusinessDenied("invalid membership grant")
        if type(claim_limit) is not int or not 1 <= claim_limit <= 100:
            raise ValueError("invalid claim limit")
        if claim_limit > 1 and (not self.collective or subject is not None or count != 1):
            raise ValueError("collective codes require enabled support, one code and no subject binding")
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("invalid code count")
        if ttl is not None and (type(ttl) is not int or not 1 <= ttl <= 2592000):
            raise ValueError("invalid redemption deadline")
        if kind in ("trial","complimentary"):
            if type(days) is not int or not 1 <= days <= 365:
                raise ValueError("invalid membership duration")
        elif days is not None:
            raise ValueError("duration must not be supplied")
        # Only a trusted server-side subject resolver may supply a verified subject.
        # The owner role does not need SELECT on external identity records.
        if subject is not None:
            if not isinstance(self.issuer,str) or not isinstance(subject,str) or not re.fullmatch(r'user_[A-Za-z0-9]{1,120}',subject):
                raise ValueError('verified subject required')
            identity = hmac.digest(self.store.pepper, ('clerk-v1:'+self.issuer+':'+subject).encode('ascii'), hashlib.sha256)
        else:
            identity = None
        codes = [secrets.token_urlsafe(32) for _ in range(count)]
        with self.store.transaction() as db:
            now = self.store._now()
            for code in codes:
                digest = self.store._digest("activation-v2", code)
                if claim_limit > 1:
                    db.execute("INSERT INTO collective_codes_v3(digest,kind,days,expires_at,claim_limit,used_count,cancelled_at) VALUES (?,?,?,?,?,0,NULL)",
                               (digest,kind,days,None if ttl is None else now+ttl,claim_limit))
                else:
                    db.execute("INSERT INTO activation_codes_v2 VALUES (?,?,?,?,?,NULL,NULL,NULL)",
                               (digest,kind,days,None if ttl is None else now+ttl,identity))
                self.store._audit(db,actor,"issue_activation",digest.hex(),kind)
        return codes

    def cancel(self, credential, code_id):
        actor = self.store._owner(credential)
        if not isinstance(code_id,str) or len(code_id)!=64:
            raise ValueError("invalid code identifier")
        digest = bytes.fromhex(code_id)
        if digest.hex()!=code_id:
            raise ValueError("invalid code identifier")
        with self.store.transaction() as db:
            changed = db.execute("UPDATE activation_codes_v2 SET cancelled_at=? WHERE digest=? AND cancelled_at IS NULL AND redeemed_at IS NULL",
                                 (self.store._now(),digest)).rowcount == 1
            if not changed and self.collective:
                changed = db.execute("UPDATE collective_codes_v3 SET cancelled_at=? WHERE digest=? AND cancelled_at IS NULL AND used_count<claim_limit",
                                     (self.store._now(),digest)).rowcount == 1
            if changed:
                self.store._audit(db,actor,"cancel_activation",code_id,"cancelled")
            return changed

    def _claim(self, db, identity, account, token, now):
        digest = self.store._digest("activation-v2",token)
        row = db.execute("SELECT kind,days,expires_at,bound_identity,redeemed_at,cancelled_at FROM activation_codes_v2 WHERE digest=?",(digest,)).fetchone()
        if row is None and self.collective:
            return self._claim_collective(db, account, digest, now)
        if not row or row[4] is not None or row[5] is not None or (row[2] is not None and now >= row[2]) or (row[3] is not None and bytes(row[3]) != identity):
            raise MembershipDenied("activation code unavailable")
        member = grant(self.store._membership(db,account),row[0],now,days=row[1])
        db.execute("INSERT INTO memberships_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET kind=excluded.kind,expires_at=excluded.expires_at,state=excluded.state",
                   (account,member.kind,member.expires_at,member.state))
        if db.execute("UPDATE activation_codes_v2 SET redeemed_account=?,redeemed_at=? WHERE digest=? AND redeemed_at IS NULL AND cancelled_at IS NULL",
                      (account,now,digest)).rowcount != 1:
            raise MembershipDenied("activation code unavailable")
        return member

    def _claim_collective(self, db, account, digest, now):
        # Both account and business staging stores share the same transaction lock.
        # The conditional update and uniqueness constraint are additional defenses.
        row = db.execute("SELECT kind,days,expires_at,claim_limit,used_count,cancelled_at FROM collective_codes_v3 WHERE digest=?", (digest,)).fetchone()
        if not row or row[5] is not None or row[4] >= row[3] or (row[2] is not None and now >= row[2]):
            raise MembershipDenied("activation code unavailable")
        if db.execute("SELECT 1 FROM collective_redemptions_v3 WHERE digest=? AND account=?", (digest,account)).fetchone():
            raise MembershipDenied("activation code unavailable")
        previous = self.store._membership(db,account)
        member = grant(previous,row[0],now,days=row[1])
        if db.execute("UPDATE collective_codes_v3 SET used_count=used_count+1 WHERE digest=? AND used_count<claim_limit AND cancelled_at IS NULL",
                      (digest,)).rowcount != 1:
            raise MembershipDenied("activation code unavailable")
        db.execute("INSERT INTO collective_redemptions_v3(digest,account,claimed_at,previous_expiry,new_expiry) VALUES (?,?,?,?,?)",
                   (digest,account,now,previous.expires_at if previous else None,member.expires_at))
        db.execute("INSERT INTO memberships_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET kind=excluded.kind,expires_at=excluded.expires_at,state=excluded.state",
                   (account,member.kind,member.expires_at,member.state))
        return member

    def register(self, issuer, subject, device, code):
        identity = self.store._identity(issuer,subject)
        device = self.store._device(device)
        account,recovery = secrets.token_hex(16),secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            now = self.store._now()
            if db.execute("SELECT 1 FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone():
                raise MembershipDenied("existing account requires sign in or recovery")
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=?",(device,)).fetchone():
                raise MembershipDenied("device already registered")
            db.execute("INSERT INTO accounts_v2 VALUES (?,?,?,?)",
                       (account,device,self.store._digest("recovery",recovery),now))
            db.execute("INSERT INTO external_identity_v2 VALUES (?,?)",(identity,account))
            member = self._claim(db,identity,account,code,now)
        return account,recovery,member

    def redeem(self, issuer, subject, device, code):
        identity = self.store._identity(issuer,subject)
        device = self.store._device(device)
        with self.store.transaction() as db:
            row = db.execute("SELECT account FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone()
            if not row:
                raise MembershipDenied("account unavailable")
            account = row[0]
            self.store._require_device(db,account,device)
            return self._claim(db,identity,account,code,self.store._now())

    def history(self, credential, account, limit=100):
        """Owner-only account history; never return raw activation codes."""
        self.store._owner(credential)
        account = self.store._account(account)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid history limit")
        with self.store.transaction() as db:
            if not db.execute("SELECT 1 FROM accounts_v2 WHERE id=?", (account,)).fetchone():
                raise MembershipDenied("unknown account")
            rows = db.execute("SELECT digest,kind,redeemed_at FROM activation_codes_v2 WHERE redeemed_account=? AND redeemed_at IS NOT NULL ORDER BY redeemed_at DESC,digest LIMIT ?", (account,limit)).fetchall()
            counts = dict(db.execute("SELECT kind,COUNT(*) FROM activation_codes_v2 WHERE redeemed_account=? AND redeemed_at IS NOT NULL GROUP BY kind", (account,)).fetchall())
            events = [{"reference":bytes(row[0]).hex()[:16],"kind":row[1],"claimed_at":row[2],"collective":False} for row in rows]
            if self.collective:
                rows = db.execute("SELECT r.digest,c.kind,r.claimed_at,r.previous_expiry,r.new_expiry FROM collective_redemptions_v3 r JOIN collective_codes_v3 c ON c.digest=r.digest WHERE r.account=? ORDER BY r.claimed_at DESC,r.digest LIMIT ?", (account,limit)).fetchall()
                events.extend({"reference":bytes(row[0]).hex()[:16],"kind":row[1],"claimed_at":row[2],"collective":True,"previous_expiry":row[3],"new_expiry":row[4]} for row in rows)
                for kind, count in db.execute("SELECT c.kind,COUNT(*) FROM collective_redemptions_v3 r JOIN collective_codes_v3 c ON c.digest=r.digest WHERE r.account=? GROUP BY c.kind", (account,)).fetchall():
                    counts[kind] = counts.get(kind,0) + count
            total = sum(int(value) for value in counts.values())
            events.sort(key=lambda item:(item["claimed_at"],item["reference"]),reverse=True)
            events = events[:limit]
            for index, event in enumerate(events):
                event["claim_number"] = total-index
            return {"account":account,"total_claims":total,"renewals":int(counts.get("renewal",0)),"events":events}

    def list(self, credential, limit=100):
        self.store._owner(credential)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid limit")
        with self.store.transaction() as db:
            rows = db.execute("SELECT digest,kind,days,expires_at,redeemed_account,redeemed_at,cancelled_at FROM activation_codes_v2 ORDER BY expires_at DESC,digest LIMIT ?",(limit,))
            result = [{"id":bytes(r[0]).hex(),"kind":r[1],"days":r[2],"expires_at":r[3],
                       "redeemed_account":r[4],"redeemed_at":r[5],"cancelled_at":r[6]} for r in rows]
            if self.collective:
                collective = db.execute("SELECT digest,kind,days,expires_at,claim_limit,used_count,cancelled_at FROM collective_codes_v3 ORDER BY expires_at DESC,digest LIMIT ?",(limit,))
                result.extend({"id":bytes(r[0]).hex(),"kind":r[1],"days":r[2],"expires_at":r[3],
                               "claim_limit":r[4],"used_count":r[5],"cancelled_at":r[6],
                               "redeemed_account":None,"redeemed_at":None} for r in collective)
                result.sort(key=lambda item: (item["expires_at"] is None, item["expires_at"] or 0, item["id"]), reverse=True)
            return result[:limit]
