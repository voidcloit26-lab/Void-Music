"""Bounded activation WSGI API. Deploy only behind a TLS reverse proxy.

One process is required because short-lived challenges and request budgets live in memory.
No owner endpoints, public key discovery, logging of requests, or client-supplied IP trust.
"""
import json
import os
import pathlib
import stat
import threading
import time
from collections import deque
from cryptography.hazmat.primitives import serialization
from guardian.access_store import AccessDenied
from guardian.device_protocol import AccessInactive, DeviceProtocol
from guardian.owner_cli import store_from_environment

ROUTES = {
    "/v1/challenge": ("public_key", "action"),
    "/v1/redeem": ("public_key", "nonce", "signature", "code"),
    "/v1/status": ("public_key", "nonce", "signature"),
}
MAX_BODY = 4096

class RequestBudget:
    def __init__(self, limit=180, window=60, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.times = deque()
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            now = self.clock()
            while self.times and self.times[0] <= now - self.window:
                self.times.popleft()
            if len(self.times) >= self.limit:
                return False
            self.times.append(now)
            return True

class ActivationAPI:
    def __init__(self, protocol, budget=None):
        self.protocol = protocol
        self.budget = budget if budget is not None else RequestBudget()

    @staticmethod
    def respond(start, status, value):
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store"),
                   ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(body)))]
        if status.startswith("429"):
            headers.append(("Retry-After", "60"))
        start(status, headers)
        return [body]

    def __call__(self, env, start):
        def reply(status, value):
            return self.respond(start, status, value)

        path = env.get("PATH_INFO", "")
        if path not in ROUTES or env.get("QUERY_STRING"):
            return reply("404 Not Found", {"error": "not_found"})
        if env.get("REQUEST_METHOD") != "POST":
            return reply("405 Method Not Allowed", {"error": "method_not_allowed"})
        if not self.budget.take():
            return reply("429 Too Many Requests", {"error": "retry_later"})
        if env.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return reply("415 Unsupported Media Type", {"error": "invalid_request"})
        try:
            size = int(env.get("CONTENT_LENGTH", ""))
        except (ValueError, TypeError):
            return reply("411 Length Required", {"error": "invalid_request"})
        if not 0 < size <= MAX_BODY:
            return reply("413 Payload Too Large", {"error": "invalid_request"})
        try:
            body = env["wsgi.input"].read(size)
            if len(body) != size:
                raise ValueError("truncated request")
            def unique_pairs(pairs):
                out = {}
                for key, value in pairs:
                    if key in out:
                        raise ValueError("duplicate key")
                    out[key] = value
                return out
            data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_pairs)
            if not isinstance(data, dict) or set(data) != set(ROUTES[path]):
                raise ValueError("unexpected fields")
            if any(not isinstance(v, str) or len(v) > 512 for v in data.values()):
                raise ValueError("invalid value")
        except (ValueError, UnicodeError, RecursionError):
            return reply("400 Bad Request", {"error": "invalid_request"})

        try:
            if path == "/v1/challenge":
                result = self.protocol.challenge(**data)
            elif path == "/v1/redeem":
                result = self.protocol.redeem(**data)
            else:
                result = self.protocol.status(**data)
        except AccessInactive:
            return reply("403 Forbidden", {"error": "access_inactive"})
        except AccessDenied:
            return reply("403 Forbidden", {"error": "access_denied"})
        except Exception:
            # Do not expose invitation data, proof material, or internal errors.
            return reply("503 Service Unavailable", {"error": "unavailable"})
        return reply("200 OK", result)

def create_app():
    store = store_from_environment()
    encoded = os.environ.get("VOID_GUARDIAN_SIGNING_KEY_B64")
    if encoded:
        import base64
        if len(encoded) > 4096:
            raise ValueError("Invalid signing key")
        key = serialization.load_der_private_key(base64.b64decode(encoded, validate=True), password=None)
        return ActivationAPI(DeviceProtocol(store, key))
    root = pathlib.Path(os.environ["VOID_GUARDIAN_STATE"])
    key_path = root / "signing-key.pem"
    info = key_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("Signing key must be an owner-only regular file (0600)")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    return ActivationAPI(DeviceProtocol(store, key))
