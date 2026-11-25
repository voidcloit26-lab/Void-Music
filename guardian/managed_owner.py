"""Separate HTTPS owner application. Never mount this on the activation API."""
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from urllib.parse import parse_qs
from guardian.activation_api import RequestBudget
from guardian.owner_web import page
from guardian.postgres_store import PostgresAccessStore

LOG = logging.getLogger("guardian.owner.audit")
HEX = re.compile(r"[0-9a-f]{64}")
HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")

class OwnerApplication:
    def __init__(self, store, host, password_digest):
        if not HOST.fullmatch(host) or "." not in host or not HEX.fullmatch(password_digest):
            raise ValueError("Invalid owner settings")
        self.store = store
        self.host = host
        self.origin = "https://" + host
        self.digest = bytes.fromhex(password_digest)
        self.csrf = secrets.token_urlsafe(32)
        self.failures = RequestBudget(limit=30, window=60)

    @staticmethod
    def reply(start, status, body=b"", extra=()):
        start(status, [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Strict-Transport-Security", "max-age=31536000"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
        ] + list(extra))
        return [body]

    def authenticated(self, env):
        value = env.get("HTTP_AUTHORIZATION", "")
        if not value.startswith("Basic ") or len(value) > 256:
            return False
        try:
            raw = base64.b64decode(value[6:], validate=True)
        except ValueError:
            return False
        user, sep, password = raw.partition(b":")
        digest = hashlib.sha256(password).digest()
        return bool(sep and user == b"owner" and hmac.compare_digest(digest, self.digest))

    def render(self, message="", code=""):
        return page(self.store, self.csrf, message, code).replace(
            b"Private invitation management \xe2\x80\x94 local development only.",
            b"Private owner console &middot; Guardian staging."
        )

    def __call__(self, env, start):
        def reply(status, body=b"", extra=()):
            return self.reply(start, status, body, extra)
        if env.get("HTTP_HOST") != self.host:
            return reply("403 Forbidden")
        path, method = env.get("PATH_INFO"), env.get("REQUEST_METHOD")
        if env.get("QUERY_STRING"):
            return reply("404 Not Found")
        if path == "/healthz" and method == "GET":
            return reply("200 OK", b"ready")
        if path != "/":
            return reply("404 Not Found")
        if not self.authenticated(env):
            if not self.failures.take():
                return reply("429 Too Many Requests", extra=(("Retry-After","60"),))
            return reply("401 Unauthorized", extra=(("WWW-Authenticate",'Basic realm="VOID Guardian Owner", charset="UTF-8"'),))
        if method not in ("GET", "POST"):
            return reply("405 Method Not Allowed")
        try:
            if method == "GET":
                return reply("200 OK", self.render())
            if env.get("HTTP_ORIGIN") != self.origin:
                return reply("403 Forbidden")
            if env.get("CONTENT_TYPE", "").split(";")[0] != "application/x-www-form-urlencoded":
                return reply("415 Unsupported Media Type")
            try:
                size = int(env.get("CONTENT_LENGTH", "0"))
                if not 0 < size <= 4096:
                    raise ValueError
                body = env["wsgi.input"].read(size)
                if len(body) != size:
                    raise ValueError
                fields = parse_qs(body.decode(), strict_parsing=True, max_num_fields=5)
                if any(len(v) != 1 for v in fields.values()):
                    raise ValueError
                f = {k:v[0] for k,v in fields.items()}
            except (ValueError, UnicodeError):
                return reply("400 Bad Request")
            if not hmac.compare_digest(f.get("csrf","").encode(), self.csrf.encode()):
                return reply("403 Forbidden")
            action = f.get("action")
            if action == "generate" and set(f) == {"csrf","action","uses","ttl"}:
                uses, ttl = int(f["uses"]), int(f["ttl"])
                if not 1 <= uses <= 1000 or ttl not in (0,3600,86400,604800):
                    raise ValueError
                code = self.store.generate(uses, ttl or None)
                LOG.info("owner_action=generate result=success")
                return reply("200 OK", self.render("Invitation generated.", code))
            if action in ("cancel","revoke") and set(f) == {"csrf","action","id"}:
                if action == "cancel":
                    if not HEX.fullmatch(f["id"]):
                        raise ValueError
                    ok = self.store.cancel_id(f["id"])
                else:
                    if not re.fullmatch(r"[1-9][0-9]{15,20}", f["id"]):
                        raise ValueError
                    ok = self.store.revoke(f["id"])
                LOG.info("owner_action=%s result=%s", action, "success" if ok else "not_found")
                return reply("200 OK", self.render("Action completed." if ok else "Not found or unavailable."))
            return reply("400 Bad Request")
        except (ValueError, KeyError):
            return reply("400 Bad Request")
        except Exception:
            LOG.warning("owner_operation_failed")
            return reply("503 Service Unavailable")

def create_app():
    # Separate service, no signing private key needed. Fail closed, never SQLite.
    host = os.environ["VOID_GUARDIAN_OWNER_HOST"]
    digest = os.environ["VOID_GUARDIAN_OWNER_PASSWORD_SHA256"]
    pepper = bytes.fromhex(os.environ["VOID_GUARDIAN_PEPPER"])
    if not HOST.fullmatch(host) or "." not in host or not HEX.fullmatch(digest) or not 32 <= len(pepper) <= 64:
        raise ValueError("Invalid owner configuration")
    store = PostgresAccessStore(os.environ["VOID_GUARDIAN_DATABASE_URL"], pepper, initialize_schema=False)
    return OwnerApplication(store, host, digest)
