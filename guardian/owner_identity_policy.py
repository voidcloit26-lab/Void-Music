"""Owner recognition from trusted Clerk profile data, never client email claims.

A configured owner is pinned to an immutable Clerk subject AND a verified
primary Gmail address. A new account using the same address is not an owner.
Only a trusted server-side Clerk profile lookup may supply the profile.
"""
import re
from guardian.business_store import BusinessDenied


class OwnerIdentityPolicy:
    def __init__(self, issuer, owners):
        if not isinstance(issuer,str) or not issuer.startswith("https://"):
            raise ValueError("configured issuer required")
        if not isinstance(owners,dict) or not 1 <= len(owners) <= 10:
            raise ValueError("explicit owner identities required")
        clean={}
        for subject,email in owners.items():
            if not isinstance(subject,str) or not re.fullmatch(r"user_[A-Za-z0-9]{1,120}",subject):
                raise ValueError("invalid owner subject")
            if not isinstance(email,str) or not re.fullmatch(r"[a-z0-9][a-z0-9._+-]{0,63}@gmail\.com",email):
                raise ValueError("registered Gmail required")
            if email in clean.values():
                raise ValueError("duplicate owner email")
            clean[subject]=email
        self.issuer,self.owners=issuer,clean

    def authorize(self, session, profile):
        if session.issuer != self.issuer or session.subject not in self.owners:
            raise BusinessDenied("owner authorization required")
        if not isinstance(profile,dict) or profile.get("id") != session.subject:
            raise BusinessDenied("owner authorization required")
        if profile.get("banned") is True or profile.get("locked") is True:
            raise BusinessDenied("owner authorization required")
        primary=profile.get("primary_email_address_id")
        emails=profile.get("email_addresses")
        if not isinstance(primary,str) or not isinstance(emails,list):
            raise BusinessDenied("owner authorization required")
        matches=[e for e in emails if isinstance(e,dict) and e.get("id")==primary]
        if len(matches)!=1:
            raise BusinessDenied("owner authorization required")
        email=matches[0]
        verification=email.get("verification")
        if (email.get("email_address")!=self.owners[session.subject] or
                not isinstance(verification,dict) or verification.get("status")!="verified"):
            raise BusinessDenied("owner authorization required")
        return session.subject

    @staticmethod
    def require_fresh_mfa(factor_age):
        # The caller must obtain fva from the verified Clerk JWT, not a request body.
        # Clerk expresses factor verification age in whole minutes. A missing
        # second factor (-1) is never accepted for privileged business operations.
        if (not isinstance(factor_age,list) or len(factor_age)!=2 or
                any(type(v) is not int or not 0 <= v <= 4 for v in factor_age)):
            raise BusinessDenied("fresh multi-factor authentication required")
