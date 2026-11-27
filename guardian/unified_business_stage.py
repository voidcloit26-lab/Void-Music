"""Separate staging business service using the same Clerk login as the app."""
import base64
import json
import os
from guardian.business_api_v2 import BusinessAPI
from guardian.stage_business_store import StageBusinessStore
from guardian.clerk_session import ClerkSessionVerifier
from guardian.clerk_profile import ClerkProfileLookup
from guardian.owner_identity_policy import OwnerIdentityPolicy
from guardian.clerk_owner_credential import ClerkOwnerCredential
from guardian.activation_codes_v2 import ActivationCodes

def create_app():
    try:
        if os.environ.get("VOID_V2_UNIFIED_BUSINESS_ENABLED")!="true":
            raise ValueError("explicit staging enablement required")
        issuer=os.environ["VOID_V2_CLERK_ISSUER"]
        policy=OwnerIdentityPolicy(issuer,json.loads(os.environ["VOID_V2_OWNER_IDENTITIES_JSON"]))
        if len(policy.owners)!=1:
            raise ValueError("one configured owner required")
        verifier=ClerkSessionVerifier(issuer=issuer,audience="void-music-api",
            public_key_pem=base64.b64decode(os.environ["VOID_V2_CLERK_RSA_PEM_B64"],validate=True))
        lookup=ClerkProfileLookup(os.environ["VOID_V2_CLERK_SECRET_KEY"])
        credential=ClerkOwnerCredential(verifier,policy,lookup)
        store=StageBusinessStore(os.environ["VOID_V2_BUSINESS_DATABASE_URL"],
            bytes.fromhex(os.environ["VOID_V2_STAGE_PEPPER"]),sandbox=True,
            owner_id=next(iter(policy.owners)),verify_owner=credential)
        with store.transaction() as db:
            db.execute("SELECT digest,kind,days,expires_at,bound_identity,redeemed_account,redeemed_at,cancelled_at FROM activation_codes_v2 LIMIT 0")
            for column in ("redeemed_account","redeemed_at"):
                if db.execute("SELECT has_column_privilege(current_user,'guardian_v2_stage.activation_codes_v2',?,'UPDATE')",(column,)).fetchone()[0]:
                    raise PermissionError("business role cannot redeem codes")
        api=BusinessAPI(store,sandbox=True,clerk_mode=True,activation=ActivationCodes(store,issuer=issuer))
    except Exception:
        raise RuntimeError("unified business staging configuration failed") from None
    def application(env,start):
        if env.get("PATH_INFO")=="/healthz" and not env.get("QUERY_STRING") and env.get("REQUEST_METHOD")=="GET":
            return BusinessAPI._reply(start,"200 OK",{"status":"ready","mode":"unified-business-staging","payments_enabled":False})
        return api(env,start)
    return application
