"""Locked staging service. Validate configured credentials without exposing them."""
import base64
import hmac
import json
import os

def reply(start, status, value):
    body = json.dumps(value, separators=(",", ":")).encode("ascii")
    start(status, [("Content-Type", "application/json"), ("Cache-Control", "no-store"),
                   ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(body)))])
    return [body]

def create_app():
    if os.environ.get("VOID_V2_STAGE_READINESS_ONLY") == "false":
        from guardian.stage_app import create_app as create_account_app
        return create_account_app()
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
    clerk_ok = False
    signing_ok = False
    try:
        from guardian.clerk_session import ClerkSessionVerifier
        ClerkSessionVerifier(issuer=os.environ["VOID_V2_CLERK_ISSUER"],
            audience="void-music-api", public_key_pem=base64.b64decode(
                os.environ["VOID_V2_CLERK_RSA_PEM_B64"], validate=True))
        clerk_ok = True
    except Exception:
        pass
    private_ok = False
    public_ok = False
    canonical = None
    supplied = None
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        raw = os.environ["VOID_V2_LEASE_PRIVATE_B64"].strip()
        key = serialization.load_der_private_key(base64.b64decode(raw, validate=True), password=None)
        if isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1):
            private_ok = True
            canonical = base64.urlsafe_b64encode(key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).rstrip(b"=").decode("ascii")
    except Exception:
        pass
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        supplied = os.environ["VOID_V2_LEASE_PUBLIC_KEY"].strip()
        der = base64.b64decode(supplied + "=" * (-len(supplied) % 4), altchars=b"-_", validate=True)
        public = serialization.load_der_public_key(der)
        public_ok = (isinstance(public, ec.EllipticCurvePublicKey)
                     and isinstance(public.curve, ec.SECP256R1)
                     and base64.urlsafe_b64encode(public.public_bytes(
                         serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                     )).rstrip(b"=").decode("ascii") == supplied)
    except Exception:
        pass
    signing_ok = bool(private_ok and public_ok and hmac.compare_digest(canonical, supplied))

    def application(env, start):
        if env.get("PATH_INFO") not in ("/", "/healthz") or env.get("QUERY_STRING"):
            return reply(start, "404 Not Found", {"error": "not_found"})
        if env.get("REQUEST_METHOD") != "GET":
            return reply(start, "405 Method Not Allowed", {"error": "method_not_allowed"})
        return reply(start, "200 OK", {
            "status": "ready" if configured and clerk_ok and signing_ok else "configuration_required",
            "mode": "staging-readiness-only", "database_verified": configured,
            "clerk_key_valid": clerk_ok, "signing_private_valid": private_ok,
            "signing_public_valid": public_ok, "signing_pair_valid": signing_ok,
            "activation_profile_configured": bool(os.environ.get("VOID_V2_CLERK_SECRET_KEY")),
            "owner_identity_configured": bool(os.environ.get("VOID_V2_OWNER_IDENTITIES_JSON")),
            "account_routes_enabled": False})
    return application
