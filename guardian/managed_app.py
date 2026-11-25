"""Strict managed-host entry point. No fallback to ephemeral SQLite.

Only the independent Guardian PostgreSQL service may use this entry point.
The public key is pinned independently to detect accidental signing-key replacement.
The health endpoint checks process readiness, not live database health, to avoid
waking the database on every platform probe.
"""
import base64
import hmac
import os
import logging
import psycopg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.activation_api import ActivationAPI
from guardian.device_protocol import DeviceProtocol, b64
from guardian.postgres_store import PostgresAccessStore

REQUIRED = ("VOID_GUARDIAN_DATABASE_URL", "VOID_GUARDIAN_PEPPER",
            "VOID_GUARDIAN_SIGNING_KEY_B64", "VOID_GUARDIAN_PUBLIC_KEY")

def config(environ):
    if any(not environ.get(key) for key in REQUIRED):
        raise ValueError("Managed Guardian requires all four deployment settings")
    if environ.get("VOID_GUARDIAN_PEPPER_FILE") or environ.get("VOID_GUARDIAN_STATE"):
        raise ValueError("Managed Guardian does not accept local state settings")
    try:
        pepper = bytes.fromhex(environ["VOID_GUARDIAN_PEPPER"])
        if not 32 <= len(pepper) <= 64:
            raise ValueError
        encoded = environ["VOID_GUARDIAN_SIGNING_KEY_B64"]
        if len(encoded) > 4096:
            raise ValueError
        key = serialization.load_der_private_key(
            base64.b64decode(encoded, validate=True), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError
        public = b64(key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        if not hmac.compare_digest(public, environ["VOID_GUARDIAN_PUBLIC_KEY"]):
            raise ValueError
    except (ValueError, TypeError, UnicodeError):
        # Never propagate the actual configuration values.
        raise ValueError("Invalid managed Guardian signing configuration") from None
    return environ["VOID_GUARDIAN_DATABASE_URL"], pepper, key

class ManagedApplication:
    def __init__(self, api):
        self.api = api

    def __call__(self, env, start):
        if env.get("PATH_INFO") == "/healthz" and not env.get("QUERY_STRING"):
            if env.get("REQUEST_METHOD") == "GET":
                return ActivationAPI.respond(start, "200 OK", {"status": "ready"})
            return ActivationAPI.respond(start, "405 Method Not Allowed", {"error": "method_not_allowed"})
        return self.api(env, start)

def database_failure_category(exc):
    # Closed vocabulary only: never emit connection strings, passwords, exception
    # repr, or raw provider error details in platform logs.
    if isinstance(exc, PermissionError):
        return "runtime_grants"
    if isinstance(exc, ValueError):
        return "connection_config"
    if isinstance(exc, psycopg.OperationalError):
        message = str(exc).lower()
        if "certificate" in message or "sslrootcert" in message or "ssl error" in message:
            return "tls_certificate"
        if "authentication" in message or "password" in message:
            return "authentication"
        if "timeout" in message or "timed out" in message:
            return "connect_timeout"
        if "translate host" in message or "name resolution" in message:
            return "dns"
        return "database_connection"
    if isinstance(exc, psycopg.Error):
        return "database_sql"
    return "unexpected"

def create_app():
    url, pepper, key = config(os.environ)
    # The PostgreSQL adapter requires verified TLS and initializes the dedicated schema.
    # No application instance is returned when initialization fails.
    try:
        store = PostgresAccessStore(url, pepper, initialize_schema=False)
    except Exception as exc:
        logging.getLogger(__name__).error('Guardian startup category: %s', database_failure_category(exc))
        raise RuntimeError("Guardian database initialization failed; check dedicated database configuration") from None
    return ManagedApplication(ActivationAPI(DeviceProtocol(store, key)))
