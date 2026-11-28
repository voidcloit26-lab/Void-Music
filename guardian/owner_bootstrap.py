"""Owner bootstrap is tied to the pinned external identity, not the device.
No owner administration credential or elevated database role is created here.
"""
import secrets
from guardian.business_store import BusinessDenied
from guardian.membership_rules import Membership, MembershipDenied

class OwnerBootstrap:
    def __init__(self, store, policy, profile_lookup):
        self.store,self.policy,self.profile_lookup=store,policy,profile_lookup

    def recognized(self, session):
        if session.issuer!=self.policy.issuer or session.subject not in self.policy.owners:
            return False
        try:
            self.policy.authorize(session,self.profile_lookup(session.subject))
            return True
        except BusinessDenied:
            return False

    def register(self, session, device):
        if not self.recognized(session):
            raise MembershipDenied("owner registration denied")
        identity=self.store._identity(session.issuer,session.subject)
        device=self.store._device(device)
        account,recovery=secrets.token_hex(16),secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            if db.execute("SELECT 1 FROM external_identity_v2 WHERE identity=?",(identity,)).fetchone():
                raise MembershipDenied("existing identity requires recovery")
            if db.execute("SELECT 1 FROM accounts_v2 WHERE device=?",(device,)).fetchone():
                raise MembershipDenied("existing device requires linking")
            db.execute("INSERT INTO accounts_v2 VALUES (?,?,?,?)",
                (account,device,self.store._digest("recovery",recovery),self.store._now()))
            db.execute("INSERT INTO external_identity_v2 VALUES (?,?)",(identity,account))
            db.execute("INSERT INTO memberships_v2 VALUES (?,?,?,?)",(account,"lifetime",None,"enabled"))
        return account,recovery,Membership("lifetime",None)

    def role(self,session):
        # A configured owner's failed identity verification is not a regular
        # customer signup. Do not silently downgrade or show a purchase prompt.
        if session.issuer != self.policy.issuer or session.subject not in self.policy.owners:
            return "member"
        if not self.recognized(session):
            raise MembershipDenied("owner identity verification required")
        return "owner"
