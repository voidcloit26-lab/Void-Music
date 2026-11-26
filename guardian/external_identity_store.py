"""External identity links for the isolated Guardian V2 store.

Only a trusted server adapter may supply a verified issuer, subject and device.
This is NOT JWT verification, an HTTP API, or a production recovery endpoint.
"""
from contextlib import closing
import hashlib
import hmac
import re
import sqlite3
from urllib.parse import urlsplit
from guardian.identity_store import IdentityStore
from guardian.membership_rules import MembershipDenied

DDL = """CREATE TABLE IF NOT EXISTS external_identity_v2 (
    identity BLOB PRIMARY KEY,
    account TEXT UNIQUE NOT NULL REFERENCES accounts_v2(id)
);"""

class ExternalIdentityStore(IdentityStore):
    def __init__(self, path, pepper, *, issuer, **kwargs):
        if not isinstance(issuer, str) or len(issuer)>256:
            raise ValueError("configured issuer required")
        url=urlsplit(issuer)
        if url.scheme!="https" or not url.hostname or url.username or url.password or url.port or url.path or url.query or url.fragment:
            raise ValueError("exact HTTPS issuer required")
        self.issuer=issuer
        super().__init__(path,pepper,**kwargs)
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.execute(DDL)

    def _identity(self, verified_issuer, verified_subject):
        if verified_issuer!=self.issuer:
            raise MembershipDenied("issuer not allowed")
        if not isinstance(verified_subject,str) or not re.fullmatch(r"user_[A-Za-z0-9]{1,120}",verified_subject):
            raise MembershipDenied("invalid subject")
        return hmac.digest(self.pepper,("clerk-v1:"+self.issuer+":"+verified_subject).encode("ascii"),hashlib.sha256)

    def link(self, account, verified_device, verified_issuer, verified_subject):
        """Require both current Guardian device proof and verified external login."""
        account,device=self._account(account),self._device(verified_device)
        identity=self._identity(verified_issuer,verified_subject)
        with self.transaction() as db:
            self._require_device(db,account,device)
            row=db.execute("SELECT identity FROM external_identity_v2 WHERE account=?",(account,)).fetchone()
            if row:
                if hmac.compare_digest(row[0],identity):
                    return False
                raise MembershipDenied("account already linked")
            if db.execute("SELECT 1 FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone():
                raise MembershipDenied("identity already linked")
            db.execute("INSERT INTO external_identity_v2 VALUES (?,?)",(identity,account))
            return True

    def resolve(self, verified_issuer, verified_subject, verified_device):
        """Login alone is insufficient: the registered device must also match."""
        identity=self._identity(verified_issuer,verified_subject)
        device=self._device(verified_device)
        with self.transaction() as db:
            row=db.execute("SELECT account FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone()
            if not row:
                raise MembershipDenied("identity not linked")
            self._require_device(db,row[0],device)
            return row[0]

    def register(self, verified_issuer, verified_subject, verified_device):
        """Create a new unactivated account atomically after device proof.

        Existing identities and devices must recover/link instead. This never
        migrates a legacy entitlement or grants membership.
        """
        import secrets
        identity=self._identity(verified_issuer,verified_subject)
        device=self._device(verified_device)
        account,recovery=secrets.token_hex(16),secrets.token_urlsafe(32)
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone():
                raise MembershipDenied("existing identity requires recovery")
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=?",(device,)).fetchone():
                raise MembershipDenied("existing device requires linking")
            db.execute("INSERT INTO accounts_v2 VALUES (?,?,?,?)",
                       (account,device,self._digest("recovery",recovery),self._now()))
            db.execute("INSERT INTO external_identity_v2 VALUES (?,?)",(identity,account))
        return account,recovery

    def recover_linked(self, verified_issuer, verified_subject, recovery, verified_new_device):
        """Require verified external identity AND single-use recovery secret."""
        import secrets
        identity=self._identity(verified_issuer,verified_subject)
        device=self._device(verified_new_device)
        digest=self._digest("recovery",recovery)
        replacement=secrets.token_urlsafe(32)
        with self.transaction() as db:
            row=db.execute("SELECT a.id,a.recovery FROM accounts_v2 a JOIN external_identity_v2 e ON e.account=a.id WHERE e.identity=?",(identity,)).fetchone()
            if not row or not hmac.compare_digest(row[1],digest):
                raise MembershipDenied("recovery denied")
            account=row[0]
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=? AND id<>?",(device,account)).fetchone():
                raise MembershipDenied("device already assigned")
            member=self._membership(db,account)
            if member and member.state=="revoked":
                raise MembershipDenied("owner review required")
            db.execute("UPDATE accounts_v2 SET device=?, recovery=? WHERE id=?",
                       (device,self._digest("recovery",replacement),account))
        return account,replacement

    def rotate_linked_recovery(self, verified_issuer, verified_subject, verified_device):
        """Recover from a lost registration/recovery response on the current device."""
        import secrets
        identity=self._identity(verified_issuer,verified_subject)
        device=self._device(verified_device)
        replacement=secrets.token_urlsafe(32)
        with self.transaction() as db:
            row=db.execute("SELECT account FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone()
            if not row:
                raise MembershipDenied("unknown identity")
            account=row[0]
            self._require_device(db,account,device)
            member=self._membership(db,account)
            if member and member.state=="revoked":
                raise MembershipDenied("owner review required")
            db.execute("UPDATE accounts_v2 SET recovery=? WHERE id=?",
                       (self._digest("recovery",replacement),account))
        return replacement
