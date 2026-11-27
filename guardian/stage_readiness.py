"""Readiness-only staging service. Customer and owner routes are closed."""
import os
from guardian.stage_store import StageStore
from guardian.account_api_v2 import AccountAPI


def create_app():
    if os.environ.get("VOID_V2_STAGE_READINESS_ONLY") != "true":
        raise RuntimeError("Readiness-only mode must be explicit")
    try:
        StageStore(os.environ["VOID_V2_STAGE_DATABASE_URL"],
                   bytes.fromhex(os.environ["VOID_V2_STAGE_PEPPER"]),
                   issuer=os.environ["VOID_V2_CLERK_ISSUER"])
    except Exception:
        raise RuntimeError("V2 staging database readiness validation failed") from None

    def application(env, start):
        if env.get("PATH_INFO") not in ("/", "/healthz") or env.get("QUERY_STRING"):
            return AccountAPI.reply(start, "404 Not Found", {"error": "not_found"})
        if env.get("REQUEST_METHOD") != "GET":
            return AccountAPI.reply(start, "405 Method Not Allowed", {"error": "method_not_allowed"})
        return AccountAPI.reply(start, "200 OK", {"status": "ready", "mode": "staging-readiness-only"})
    return application
