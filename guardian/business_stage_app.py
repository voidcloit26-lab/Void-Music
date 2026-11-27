"""Independent V2 business staging factory; no customer routes or payment API."""
import json
import os
import re

from guardian.business_api_v2 import BusinessAPI, unique, invalid_constant
from guardian.business_sessions_v2 import BusinessSessions
from guardian.business_store import BusinessDenied
from guardian.stage_business_store import StageBusinessStore


def create_app():
    try:
        if os.environ.get("VOID_V2_BUSINESS_STAGE_ENABLED") != "true":
            raise ValueError("explicit staging enablement required")
        owner_id = os.environ["VOID_V2_BUSINESS_OWNER_ID"]
        # Resolve the store and verifier without exposing credentials or enabling
        # any request before both objects have successfully initialized.
        sessions = None
        def verify(token):
            if sessions is None:
                raise BusinessDenied("owner authentication unavailable")
            return sessions.verify(token)
        store = StageBusinessStore(os.environ["VOID_V2_BUSINESS_DATABASE_URL"],
            bytes.fromhex(os.environ["VOID_V2_STAGE_PEPPER"]), sandbox=True,
            owner_id=owner_id, verify_owner=verify)
        sessions = BusinessSessions(store, owner_id=owner_id,
            salt=bytes.fromhex(os.environ["VOID_V2_BUSINESS_PASSWORD_SALT"]),
            digest=bytes.fromhex(os.environ["VOID_V2_BUSINESS_PASSWORD_HASH"]),
            scope=bytes.fromhex(os.environ["VOID_V2_BUSINESS_SESSION_SCOPE"]))
        api = BusinessAPI(store, sandbox=True)
    except Exception:
        raise RuntimeError("V2 business staging configuration failed") from None
    return BusinessApplication(sessions, api)


class BusinessApplication:
    def __init__(self, sessions, api):
        self.sessions, self.api = sessions, api

    def __call__(self, env, start):
        def reply(status, data):
            return BusinessAPI._reply(start, status, data)
        path, method = env.get("PATH_INFO"), env.get("REQUEST_METHOD")
        if env.get("QUERY_STRING"):
            return reply("404 Not Found", {"error":"not_found"})
        if env.get("HTTP_ORIGIN") or env.get("HTTP_COOKIE"):
            return reply("403 Forbidden", {"error":"access_denied"})
        if path == "/healthz":
            if method == "GET":
                return reply("200 OK", {"status":"ready","mode":"business-staging","payments_enabled":False})
            return reply("405 Method Not Allowed", {"error":"method_not_allowed"})
        if path not in ("/owner/v2/login", "/owner/v2/logout"):
            return self.api(env, start)
        if method != "POST":
            return reply("405 Method Not Allowed", {"error":"method_not_allowed"})
        if env.get("CONTENT_TYPE","").split(";",1)[0].strip().lower() != "application/json":
            return reply("415 Unsupported Media Type", {"error":"invalid_request"})
        try:
            size = int(env.get("CONTENT_LENGTH",""))
            if not 0 < size <= 4096:
                raise ValueError("invalid size")
            raw = env["wsgi.input"].read(size)
            if len(raw) != size:
                raise ValueError("truncated")
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)
            if not isinstance(data,dict):
                raise ValueError("invalid fields")
            if path.endswith("/login"):
                if set(data) != {"owner","password"}:
                    raise ValueError("invalid fields")
                token = self.sessions.login(data["owner"], data["password"])
                return reply("200 OK", {"token":token,"expires_in":300})
            auth = env.get("HTTP_AUTHORIZATION","")
            if data or not isinstance(auth,str) or not re.fullmatch(r"Bearer [A-Za-z0-9_-]{43}",auth):
                raise BusinessDenied("owner authorization required")
            self.sessions.verify(auth[7:])
            return reply("200 OK", {"ok":self.sessions.logout(auth[7:])})
        except BusinessDenied:
            return reply("401 Unauthorized", {"error":"owner_auth_required"})
        except (ValueError,TypeError,UnicodeError,RecursionError):
            return reply("400 Bad Request", {"error":"invalid_request"})
        except Exception:
            return reply("503 Service Unavailable", {"error":"unavailable"})
