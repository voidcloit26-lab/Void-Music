"""Fail-closed entry point for the dedicated V2 Business staging service."""
import os
from guardian.business_api_v2 import BusinessAPI

REQUIRED = ("VOID_V2_CLERK_ISSUER", "VOID_V2_CLERK_RSA_PEM_B64",
            "VOID_V2_CLERK_SECRET_KEY", "VOID_V2_OWNER_IDENTITIES_JSON",
            "VOID_V2_STAGE_PEPPER", "VOID_V2_BUSINESS_DATABASE_URL")

def create_app():
    enabled = os.environ.get("VOID_V2_UNIFIED_BUSINESS_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise RuntimeError("Invalid explicit Business stage switch")
    if enabled == "true":
        if not all(os.environ.get(name) for name in REQUIRED):
            raise RuntimeError("Missing Business staging configuration")
        from guardian.unified_business_stage import create_app as create_business
        return create_business()

    def application(env, start):
        if env.get("QUERY_STRING") or env.get("PATH_INFO") != "/healthz":
            return BusinessAPI._reply(start, "404 Not Found", {"error":"not_found"})
        if env.get("REQUEST_METHOD") != "GET":
            return BusinessAPI._reply(start, "405 Method Not Allowed", {"error":"method_not_allowed"})
        return BusinessAPI._reply(start, "200 OK", {
            "status":"configuration_required", "mode":"business-readiness-only",
            "owner_routes_enabled":False, "payments_enabled":False})
    return application
