"""Sandbox owner service. Not an HTTP route or production authentication system.

The injected verifier must authenticate a separate owner credential. Customer
Clerk sessions are not owner credentials. All writes and their audit events
share one database transaction. No real payment acceptance or release publishing.
"""
from contextlib import closing
import re
import secrets
import sqlite3
from guardian.identity_store import IdentityStore
from guardian.membership_rules import Membership, MembershipDenied, grant

DDL = """
CREATE TABLE IF NOT EXISTS business_settings_v2 (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    usd_cents INTEGER NOT NULL CHECK(usd_cents BETWEEN 1 AND 1000000)
);
INSERT INTO business_settings_v2 VALUES (1,500) ON CONFLICT(singleton) DO NOTHING;
CREATE TABLE IF NOT EXISTS business_audit_v2 (
    id INTEGER PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

class BusinessDenied(PermissionError):
    pass

class BusinessStore(IdentityStore):
    def __init__(self,path,pepper,*,sandbox=False,owner_id,verify_owner,**kwargs):
        if sandbox is not True:
            raise BusinessDenied("sandbox only")
        if not isinstance(owner_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",owner_id):
            raise ValueError("invalid configured owner")
        if not callable(verify_owner):
            raise ValueError("owner verifier required")
        self.owner_id,self.verify_owner=owner_id,verify_owner
        super().__init__(path,pepper,**kwargs)
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.executescript(DDL)

    def _owner(self,credential):
        # A trusted independent verifier must return (actor, fresh_auth_time).
        # Never consume identity or authentication timestamps from a request body.
        try:
            actor,auth_time=self.verify_owner(credential)
            now=self._now()
            if actor!=self.owner_id or type(auth_time) is not int or not 0<=now-auth_time<=300:
                raise BusinessDenied("owner authorization required")
        except Exception as exc:
            raise BusinessDenied("owner authorization required") from exc
        return actor

    def _audit(self,db,actor,action,target,detail):
        db.execute("INSERT INTO business_audit_v2(actor,action,target,detail,created_at) VALUES (?,?,?,?,?)",
                   (actor,action,target,detail,self._now()))

    def price(self,credential):
        self._owner(credential)
        with self.transaction() as db:
            return db.execute("SELECT usd_cents FROM business_settings_v2 WHERE singleton=1").fetchone()[0]

    def change_price(self,credential,cents):
        actor=self._owner(credential)
        if type(cents) is not int or not 1<=cents<=1000000:
            raise ValueError("invalid USD price")
        with self.transaction() as db:
            old=db.execute("SELECT usd_cents FROM business_settings_v2 WHERE singleton=1").fetchone()[0]
            db.execute("UPDATE business_settings_v2 SET usd_cents=? WHERE singleton=1",(cents,))
            self._audit(db,actor,"price","USD",f"{old}->{cents}")
        return cents

    def owner_issue_free(self,credential,account,kind,*,days=None,ttl=86400):
        actor=self._owner(credential)
        account=self._account(account)
        if kind not in ("lifetime","trial","complimentary"):
            raise BusinessDenied("paid issuance disabled")
        if type(ttl) is not int or not 1<=ttl<=604800:
            raise ValueError("invalid invitation lifetime")
        token=secrets.token_urlsafe(32)
        with self.transaction() as db:
            now=self._now()
            if not db.execute("SELECT 1 FROM accounts_v2 WHERE id=?",(account,)).fetchone():
                raise MembershipDenied("unknown account")
            grant(self._membership(db,account),kind,now,days=days)
            db.execute("INSERT INTO invitations_v2 VALUES (?,?,?,?,?,NULL)",
                       (self._digest("invite",token),account,kind,days,now+ttl))
            self._audit(db,actor,"issue_free",account,kind)
        return token

    def change_state(self,credential,account,state):
        actor=self._owner(credential)
        account=self._account(account)
        if state not in ("enabled","suspended","revoked"):
            raise ValueError("invalid state")
        with self.transaction() as db:
            member=self._membership(db,account)
            if member is None:
                raise MembershipDenied("no membership")
            # Revocation is terminal here. Reinstatement requires a separately
            # reviewed recovery workflow; suspension is reversible.
            if member.state=="revoked" and state!="revoked":
                raise BusinessDenied("revoked membership requires review")
            if member.state==state:
                return False
            db.execute("UPDATE memberships_v2 SET state=? WHERE account=?",(state,account))
            self._audit(db,actor,"membership_state",account,f"{member.state}->{state}")
            return True

    def summary(self,credential):
        self._owner(credential)
        with self.transaction() as db:
            now=self._now()
            accounts=db.execute("SELECT count(*) FROM accounts_v2").fetchone()[0]
            counts={k:0 for k in ("active","expired","suspended","revoked")}
            types={k:0 for k in ("annual","lifetime","trial","complimentary")}
            for kind,expiry,state in db.execute("SELECT kind,expires_at,state FROM memberships_v2"):
                counts[Membership(kind,expiry,state).status(now)]+=1
                types[kind]+=1
            return {"accounts":accounts,"membership_status":counts,"membership_types":types,
                    "annual_price_usd_cents":db.execute("SELECT usd_cents FROM business_settings_v2 WHERE singleton=1").fetchone()[0],
                    "payments_enabled":False}

    def member(self,credential,account):
        self._owner(credential)
        account=self._account(account)
        with self.transaction() as db:
            row=db.execute("SELECT created_at FROM accounts_v2 WHERE id=?",(account,)).fetchone()
            if not row:
                raise MembershipDenied("unknown account")
            m=self._membership(db,account)
            return {"account":account,"created_at":row[0],"kind":m.kind if m else None,
                    "expires_at":m.expires_at if m else None,
                    "status":m.status(self._now()) if m else "unactivated"}

    def audit(self,credential,limit=50):
        self._owner(credential)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid limit")
        with self.transaction() as db:
            return [dict(zip(("id","actor","action","target","detail","created_at"),row))
                    for row in db.execute("SELECT id,actor,action,target,detail,created_at FROM business_audit_v2 ORDER BY id DESC LIMIT ?",(limit,))]
