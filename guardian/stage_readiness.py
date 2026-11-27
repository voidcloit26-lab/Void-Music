"""Locked staging service. No account or owner routes are exposed."""
import json
import os


def reply(start, status, value):
    body = json.dumps(value, separators=(",", ":")).encode("ascii")
    start(status, [("Content-Type", "application/json"), ("Cache-Control", "no-store"),
                   ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(body)))])
    return [body]


def create_app():
    if os.environ.get("VOID_V2_STAGE_READINESS_ONLY") != "true":
        raise RuntimeError("Readiness-only mode must be explicit")
    configured = all(os.environ.get(k) for k in (
        "VOID_V2_STAGE_DATABASE_URL", "VOID_V2_STAGE_PEPPER", "VOID_V2_CLERK_ISSUER"))
    if configured:
        try:
            from guardian.stage_store import StageStore
            StageStore(os.environ["VOID_V2_STAGE_DATABASE_URL"],
                       bytes.fromhex(os.environ["VOID_V2_STAGE_PEPPER"]),
                       issuer=os.environ["VOID_V2_CLERK_ISSUER"])
        except Exception:
            raise RuntimeError("V2 staging database readiness validation failed") from None

    def application(env, start):
        if env.get("PATH_INFO") not in ("/", "/healthz") or env.get("QUERY_STRING"):
            return reply(start, "404 Not Found", {"error": "not_found"})
        if env.get("REQUEST_METHOD") != "GET":
            return reply(start, "405 Method Not Allowed", {"error": "method_not_allowed"})
        return reply(start, "200 OK", {
            "status": "ready" if configured else "configuration_required",
            "mode": "staging-readiness-only",
            "database_verified": configured,
            "account_routes_enabled": False})
    return application
