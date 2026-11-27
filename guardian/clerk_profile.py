"""Server-only Clerk profile lookup for verified onboarding and owner identity.
Never expose the backend secret to the Android app or follow HTTP redirects.
"""
import json
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from guardian.clerk_session import SessionDenied

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class ClerkProfileLookup:
    def __init__(self, secret):
        if not isinstance(secret,str) or not re.fullmatch(r"sk_test_[A-Za-z0-9_-]{8,512}",secret):
            raise ValueError("Clerk development backend credential required")
        self._secret=secret
        self._opener=build_opener(NoRedirect())

    def __call__(self, subject):
        if not isinstance(subject,str) or not re.fullmatch(r"user_[A-Za-z0-9]{1,120}",subject):
            raise SessionDenied("invalid subject")
        request=Request("https://api.clerk.com/v1/users/"+subject,
                        headers={"Authorization":"Bearer "+self._secret,"Accept":"application/json"})
        try:
            with self._opener.open(request,timeout=8) as response:
                if response.status!=200 or response.headers.get_content_type()!="application/json":
                    raise ValueError("invalid response")
                raw=response.read(262145)
                if len(raw)>262144:
                    raise ValueError("response too large")
                profile=json.loads(raw)
                if not isinstance(profile,dict) or profile.get("id")!=subject:
                    raise ValueError("profile mismatch")
        except Exception:
            raise SessionDenied("identity verification unavailable") from None
        return profile

def verified_primary_email(subject, profile):
    if (not isinstance(profile,dict) or profile.get("id")!=subject or
            profile.get("banned") is True or profile.get("locked") is True):
        raise SessionDenied("verified email required")
    primary=profile.get("primary_email_address_id")
    addresses=profile.get("email_addresses")
    if not isinstance(primary,str) or not isinstance(addresses,list):
        raise SessionDenied("verified email required")
    matches=[a for a in addresses if isinstance(a,dict) and a.get("id")==primary]
    if len(matches)!=1:
        raise SessionDenied("verified email required")
    item=matches[0]
    email=item.get("email_address")
    verification=item.get("verification")
    if (not isinstance(email,str) or not 3<=len(email)<=254 or "@" not in email or
            not isinstance(verification,dict) or verification.get("status")!="verified"):
        raise SessionDenied("verified email required")
    return email
