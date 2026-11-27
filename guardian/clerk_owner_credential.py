"""Unified Clerk owner authorization. Never trusts a client-supplied role."""
import time
from guardian.business_store import BusinessDenied

class ClerkOwnerCredential:
    def __init__(self, verifier, policy, lookup, *, clock=time.time):
        self.verifier,self.policy,self.lookup,self.clock=verifier,policy,lookup,clock
    def __call__(self, token):
        try:
            session=self.verifier.verify(token)
            if session.issuer!=self.policy.issuer or session.subject not in self.policy.owners:
                raise BusinessDenied("owner authorization required")
            now=int(self.clock())
            if type(session.issued_at) is not int or not 0<=now-session.issued_at<=300:
                raise BusinessDenied("fresh authentication required")
            age=list(session.factor_age) if session.factor_age is not None else None
            self.policy.require_fresh_mfa(age)
            # Ages are rounded down to whole minutes; conservatively add a minute.
            auth_time=session.issued_at-60*(max(age)+1)
            if not 0<=now-auth_time<=300:
                raise BusinessDenied("fresh authentication required")
            owner=self.policy.authorize(session,self.lookup(session.subject))
            return owner,auth_time
        except Exception:
            raise BusinessDenied("owner authorization required") from None
