"""Separate HTTPS owner application. Never mount this on the activation API."""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs
from guardian.activation_api import RequestBudget
from guardian.owner_web import page
from guardian.postgres_store import PostgresAccessStore
from guardian.native_owner_sessions import NativeOwnerSessions, NATIVE_SESSION_SECONDS

LOG = logging.getLogger("guardian.owner.audit")
HEX = re.compile(r"[0-9a-f]{64}")
EMAIL = re.compile(r"[a-z0-9][a-z0-9._+-]{0,63}@gmail\.com")
COOKIE = "__Host-guardian"
SESSION_SECONDS = 1800

def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1, dklen=32, maxmem=256*1024*1024)

def settings_valid(host, email, salt_hex, digest):
    return bool(HOST.fullmatch(host) and "." in host and EMAIL.fullmatch(email) and HEX.fullmatch(salt_hex) and HEX.fullmatch(digest))
HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")

class OwnerApplication:
    def __init__(self, store, host, email, salt_hex, password_digest, clock=time.monotonic, durable_native=None):
        if not settings_valid(host, email, salt_hex, password_digest):
            raise ValueError("Invalid owner settings")
        self.store = store
        self.host = host
        self.origin = "https://" + host
        self.digest = bytes.fromhex(password_digest)
        self.email = email
        self.salt = bytes.fromhex(salt_hex)
        self.clock = clock
        self.sessions = {}
        self.native_sessions = {}
        self.durable_native = durable_native
        self.lock = threading.Lock()
        self.login_lock = threading.Lock()
        self.failures = RequestBudget(limit=5, window=60)

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

    def session(self, env):
        try:
            cookies = SimpleCookie(env.get("HTTP_COOKIE", "")[:4096])
            token = cookies[COOKIE].value if COOKIE in cookies else ""
        except CookieError:
            return "", None
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return "", None
        with self.lock:
            now = self.clock()
            self.sessions = {k:v for k,v in self.sessions.items() if v[1] > now}
            return token, self.sessions.get(token)

    def cookie(self, token="", age=0):
        return ("Set-Cookie", COOKIE+"="+token+"; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age="+str(age))

    def login_page(self):
        return b"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VOID Guardian | Owner Login</title><style>body{background:#101016;color:#eee;font:16px system-ui;padding:24px}main{max-width:380px;margin:12vh auto;background:#1b1b25;padding:28px;border-radius:18px}label{display:block;margin:16px 0}input,button{display:block;box-sizing:border-box;width:100%;padding:12px;margin-top:6px;background:#292536;color:white;border:1px solid #655c78;border-radius:8px;font:inherit}button{background:#493673}</style><main><h1>VOID Guardian</h1><p>Private owner access</p><form method="post" action="/login"><label>Gmail address<input type="email" name="email" autocomplete="username" required maxlength="128"></label><label>Guardian password<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label><p>Use your separate Guardian password, not your Google password.</p><button>Sign in</button></form></main></html>"""

    def fields(self, env):
        if env.get("CONTENT_TYPE", "").split(";")[0] != "application/x-www-form-urlencoded":
            raise ValueError
        size = int(env.get("CONTENT_LENGTH", "0"))
        if not 0 < size <= 4096:
            raise ValueError
        body = env["wsgi.input"].read(size)
        if len(body) != size:
            raise ValueError
        fields = parse_qs(body.decode(), strict_parsing=True, max_num_fields=5)
        if any(len(v) != 1 for v in fields.values()):
            raise ValueError
        return {k:v[0] for k,v in fields.items()}

    def render(self, csrf, message="", code=""):
        body = page(self.store, csrf, message, code).replace(
            b"Private invitation management \xe2\x80\x94 local development only.",
            b"Private owner console &middot; Guardian staging."
        )
        logout = ('<form method="post" action="/logout"><input type="hidden" name="csrf" value="'+csrf+'"><button>Sign out</button></form>').encode()
        return body.replace(b"</main>", logout+b"</main>")

    def native(self, env, start):
        # JSON-only native interface. Browser cookies and Origin are never accepted
        # as authority. No CORS headers or browser credential propagation.
        def reply(status, obj):
            body = json.dumps(obj, separators=(",", ":")).encode()
            start(status, [("Content-Type", "application/json"), ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                ("Strict-Transport-Security", "max-age=31536000")])
            return [body]
        path = env.get("PATH_INFO")
        if path not in ("/native/v1/login", "/native/v1/list", "/native/v1/generate", "/native/v1/cancel", "/native/v1/revoke", "/native/v1/logout"):
            return reply("404 Not Found", {"error":"not_found"})
        if env.get("HTTP_ORIGIN"):
            return reply("403 Forbidden", {"error":"denied"})
        if env.get("REQUEST_METHOD") != "POST":
            return reply("405 Method Not Allowed", {"error":"method"})
        try:
            size = int(env.get("CONTENT_LENGTH", "0"))
            if env.get("CONTENT_TYPE", "").split(";")[0] != "application/json" or not 0 < size <= 4096:
                raise ValueError
            raw = env["wsgi.input"].read(size)
            if len(raw) != size:
                raise ValueError
            f = json.loads(raw)
            if not isinstance(f, dict):
                raise ValueError
        except (ValueError, UnicodeError, TypeError):
            return reply("400 Bad Request", {"error":"invalid_request"})
        if path == "/native/v1/login":
            if set(f) != {"email","password"} or not all(isinstance(f[k], str) for k in f) or len(f["email"]) > 128 or len(f["password"]) > 256:
                return reply("400 Bad Request", {"error":"invalid_request"})
            if not self.failures.take() or not self.login_lock.acquire(blocking=False):
                return reply("429 Too Many Requests", {"error":"try_later"})
            try:
                digest = password_hash(f["password"], self.salt)
            finally:
                self.login_lock.release()
            if not (hmac.compare_digest(digest,self.digest) and hmac.compare_digest(f["email"].strip().lower().encode(), self.email.encode())):
                LOG.info("native_owner_login result=denied")
                return reply("401 Unauthorized", {"error":"invalid_credentials"})
            token = secrets.token_urlsafe(32)
            try:
                with self.lock:
                    if self.durable_native is not None:
                        self.durable_native.replace(token)
                        self.native_sessions.clear()
                    else:
                        self.native_sessions = {token:self.clock()+SESSION_SECONDS}
                    self.sessions.clear()
            except Exception:
                LOG.warning("native_owner_session_store_unavailable")
                return reply("503 Service Unavailable", {"error":"unavailable"})
            LOG.info("native_owner_login result=success")
            return reply("200 OK", {"token":token,"expires_in":NATIVE_SESSION_SECONDS if self.durable_native is not None else SESSION_SECONDS})
        auth = env.get("HTTP_AUTHORIZATION", "")
        if not re.fullmatch(r"Bearer [A-Za-z0-9_-]{43}", auth):
            return reply("401 Unauthorized", {"error":"session_expired"})
        token = auth[7:]
        try:
            with self.lock:
                if self.durable_native is not None:
                    if not self.durable_native.valid(token):
                        return reply("401 Unauthorized", {"error":"session_expired"})
                    if path == "/native/v1/logout" and not f:
                        self.durable_native.revoke(token)
                        return reply("200 OK", {"ok":True})
                else:
                    now = self.clock()
                    self.native_sessions = {k:v for k,v in self.native_sessions.items() if v > now}
                    if token not in self.native_sessions:
                        return reply("401 Unauthorized", {"error":"session_expired"})
                    if path == "/native/v1/logout" and not f:
                        self.native_sessions.pop(token, None)
                        return reply("200 OK", {"ok":True})
        except Exception:
            LOG.warning("native_owner_session_store_unavailable")
            return reply("503 Service Unavailable", {"error":"unavailable"})
        try:
            if path == "/native/v1/list" and not f:
                invitations = self.store.list_invitations()
                devices = self.store.list_activations()
                return reply("200 OK", {"invitations":invitations[:500],
                    "devices":[{k:v for k,v in row.items() if k != "device_fingerprint"} for row in devices[:500]],
                    "truncated":len(invitations)>500 or len(devices)>500})
            if path == "/native/v1/generate" and set(f) == {"uses","ttl"}:
                uses, ttl = f["uses"], f["ttl"]
                if type(uses) is not int or type(ttl) is not int or not 1 <= uses <= 1000 or ttl not in (0,3600,86400,604800):
                    raise ValueError
                code = self.store.generate(uses, ttl or None)
                LOG.info("native_owner_action=generate result=success")
                return reply("200 OK", {"code":code})
            if path in ("/native/v1/cancel","/native/v1/revoke") and set(f) == {"id"} and isinstance(f["id"], str):
                if path.endswith("/cancel"):
                    if not HEX.fullmatch(f["id"]):
                        raise ValueError
                    ok = self.store.cancel_id(f["id"])
                else:
                    if not re.fullmatch(r"[1-9][0-9]{15,20}", f["id"]):
                        raise ValueError
                    ok = self.store.revoke(f["id"])
                LOG.info("native_owner_action=%s result=%s", path.rsplit("/",1)[-1], "success" if ok else "not_found")
                return reply("200 OK", {"ok":ok})
            return reply("400 Bad Request", {"error":"invalid_request"})
        except (ValueError, KeyError):
            return reply("400 Bad Request", {"error":"invalid_request"})
        except Exception:
            LOG.warning("native_owner_operation_failed")
            return reply("503 Service Unavailable", {"error":"unavailable"})

    def __call__(self, env, start):
        def reply(status, body=b"", extra=()):
            return self.reply(start, status, body, extra)
        if env.get("HTTP_HOST") != self.host:
            return reply("403 Forbidden")
        path, method = env.get("PATH_INFO"), env.get("REQUEST_METHOD")
        if env.get("QUERY_STRING"):
            return reply("404 Not Found")
        if path.startswith("/native/"):
            return self.native(env, start)
        if path == "/healthz" and method == "GET":
            return reply("200 OK", b"ready")
        if path not in ("/", "/login", "/logout"):
            return reply("404 Not Found")
        if method not in ("GET", "POST"):
            return reply("405 Method Not Allowed")
        token, session = self.session(env)
        if path == "/login":
            if method != "POST":
                return reply("303 See Other", extra=(("Location","/"),))
            if env.get("HTTP_ORIGIN") != self.origin:
                return reply("403 Forbidden")
            try:
                f = self.fields(env)
                if set(f) != {"email","password"} or len(f["password"]) > 256 or len(f["email"]) > 128:
                    raise ValueError
            except (ValueError, UnicodeError):
                return reply("400 Bad Request")
            if not self.failures.take() or not self.login_lock.acquire(blocking=False):
                return reply("429 Too Many Requests", extra=(("Retry-After","60"),))
            try:
                digest = password_hash(f["password"], self.salt)
            finally:
                self.login_lock.release()
            if not (hmac.compare_digest(digest,self.digest) and hmac.compare_digest(f["email"].strip().lower().encode(),self.email.encode())):
                LOG.info("owner_login result=denied")
                return reply("401 Unauthorized", self.login_page())
            new = secrets.token_urlsafe(32)
            try:
                with self.lock:
                    if self.durable_native is not None:
                        self.durable_native.clear()
                    self.sessions.clear()
                    self.native_sessions.clear()
                    self.sessions[new] = (secrets.token_urlsafe(32), self.clock()+SESSION_SECONDS)
            except Exception:
                LOG.warning("native_owner_session_store_unavailable")
                return reply("503 Service Unavailable")
            LOG.info("owner_login result=success")
            return reply("303 See Other", extra=(("Location","/"),self.cookie(new, SESSION_SECONDS)))
        if not session:
            return reply("200 OK", self.login_page()) if path == "/" and method == "GET" else reply("401 Unauthorized")
        csrf = session[0]
        try:
            if method == "GET":
                return reply("200 OK", self.render(csrf)) if path == "/" else reply("405 Method Not Allowed")
            if env.get("HTTP_ORIGIN") != self.origin:
                return reply("403 Forbidden")
            try:
                f = self.fields(env)
            except (ValueError, UnicodeError):
                return reply("400 Bad Request")
            if not hmac.compare_digest(f.get("csrf","").encode(), csrf.encode()):
                return reply("403 Forbidden")
            if path == "/logout":
                if set(f) != {"csrf"}:
                    return reply("400 Bad Request")
                with self.lock:
                    self.sessions.pop(token,None)
                LOG.info("owner_logout result=success")
                return reply("303 See Other", extra=(("Location","/"),self.cookie()))
            action = f.get("action")
            if action == "generate" and set(f) == {"csrf","action","uses","ttl"}:
                uses, ttl = int(f["uses"]), int(f["ttl"])
                if not 1 <= uses <= 1000 or ttl not in (0,3600,86400,604800):
                    raise ValueError
                code = self.store.generate(uses, ttl or None)
                LOG.info("owner_action=generate result=success")
                return reply("200 OK", self.render(csrf, "Invitation generated.", code))
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
                return reply("200 OK", self.render(csrf, "Action completed." if ok else "Not found or unavailable."))
            return reply("400 Bad Request")
        except (ValueError, KeyError):
            return reply("400 Bad Request")
        except Exception:
            LOG.warning("owner_operation_failed")
            return reply("503 Service Unavailable")

def create_app():
    # Separate service, no signing private key needed. Fail closed, never SQLite.
    host = os.environ["VOID_GUARDIAN_OWNER_HOST"]
    email = os.environ["VOID_GUARDIAN_OWNER_EMAIL"].strip().lower()
    # Render's private environment is an optional bootstrap source. Prefer the
    # offline salted verifier when available. Never accept a Google password.
    password = os.environ.pop("VOID_GUARDIAN_OWNER_PASSWORD", "")
    salt = os.environ.get("VOID_GUARDIAN_OWNER_PASSWORD_SALT", "")
    digest = os.environ.get("VOID_GUARDIAN_OWNER_PASSWORD_SCRYPT", "")
    if password:
        if salt or digest or not 16 <= len(password) <= 256:
            raise ValueError("Invalid owner password configuration")
        salt = secrets.token_hex(32)
        digest = password_hash(password, bytes.fromhex(salt)).hex()
    pepper = bytes.fromhex(os.environ["VOID_GUARDIAN_PEPPER"])
    if not settings_valid(host, email, salt, digest) or not 32 <= len(pepper) <= 64:
        raise ValueError("Invalid owner configuration")
    store = PostgresAccessStore(os.environ["VOID_GUARDIAN_DATABASE_URL"], pepper, initialize_schema=False)
    durable = None
    if os.environ.get("VOID_GUARDIAN_DURABLE_NATIVE_SESSIONS") == "true":
        # Bind stored session hashes to the current owner credentials. The
        # plaintext bootstrap password (if configured) is never stored in DB.
        # A password or verifier change invalidates existing sessions.
        credential = ("password:" + password) if password else ("verifier:" + salt + ":" + digest)
        scope = hmac.digest(pepper, ("VOID-owner-scope-v1:" + email + ":" + credential).encode(), hashlib.sha256)
        durable = NativeOwnerSessions(store, scope)
    return OwnerApplication(store, host, email, salt, digest, durable_native=durable)
