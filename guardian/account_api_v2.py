"""Standalone V2 WSGI adapter; not mounted on any deployed service.

Requires a trusted TLS proxy and externally enforced per-client rate limits.
Single-process sandbox only until challenges have shared durable storage.
"""
import json

from guardian.access_store import AccessDenied
from guardian.activation_api import RequestBudget
from guardian.account_protocol_v2 import MAX_BODY
from guardian.clerk_session import SessionDenied
from guardian.cloud_store import RevisionConflict
from guardian.membership_rules import MembershipDenied
from guardian.version_gate import UpdateRequired

ROUTES = {
    "/v2/challenge": {"public_key","action","body"},
    "/v2/execute": {"public_key","nonce","signature","action","body"},
}

def unique_pairs(pairs):
    out = {}
    for k,v in pairs:
        if k in out:
            raise ValueError("duplicate JSON key")
        out[k] = v
    return out

def reject_constant(value):
    raise ValueError("invalid JSON constant")

class AccountAPI:
    def __init__(self, protocol, *, sandbox=False, budget=None):
        if sandbox is not True:
            raise PermissionError("sandbox only")
        self.protocol = protocol
        self.budget = budget if budget is not None else RequestBudget(limit=120)

    @staticmethod
    def reply(start, status, value):
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        headers = [("Content-Type","application/json"),("Cache-Control","no-store"),
                   ("X-Content-Type-Options","nosniff"),("Content-Length",str(len(body)))]
        if status.startswith("429"):
            headers.append(("Retry-After","60"))
        start(status,headers)
        return [body]

    def __call__(self, env, start):
        def reply(status, value):
            return self.reply(start,status,value)
        path=env.get("PATH_INFO","")
        if path not in ROUTES or env.get("QUERY_STRING"):
            return reply("404 Not Found",{"error":"not_found"})
        if env.get("REQUEST_METHOD")!="POST":
            return reply("405 Method Not Allowed",{"error":"method_not_allowed"})
        try:
            allowed = self.budget.take()
        except Exception:
            return reply("503 Service Unavailable",{"error":"unavailable"})
        if not allowed:
            return reply("429 Too Many Requests",{"error":"retry_later"})
        auth=env.get("HTTP_AUTHORIZATION","")
        if not isinstance(auth,str) or not auth.startswith("Bearer ") or len(auth)>8199 or " " in auth[7:] or not auth[7:]:
            return reply("401 Unauthorized",{"error":"invalid_session"})
        if env.get("CONTENT_TYPE","").split(";",1)[0].strip().lower()!="application/json":
            return reply("415 Unsupported Media Type",{"error":"invalid_request"})
        try:
            length=int(env.get("CONTENT_LENGTH",""))
        except (TypeError,ValueError):
            return reply("411 Length Required",{"error":"invalid_request"})
        if not 0<length<=MAX_BODY+4096:
            return reply("413 Payload Too Large",{"error":"invalid_request"})
        try:
            raw=env["wsgi.input"].read(length)
            if len(raw)!=length:
                raise ValueError("truncated")
            data=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_pairs,parse_constant=reject_constant)
            if not isinstance(data,dict) or set(data)!=ROUTES[path]:
                raise ValueError("invalid fields")
            if any(not isinstance(data[k],str) or len(data[k])>256 for k in ROUTES[path]-{"body"}):
                raise ValueError("invalid field")
            if not isinstance(data["body"],dict):
                raise ValueError("invalid body")
            method=self.protocol.challenge if path=="/v2/challenge" else self.protocol.execute
            result=method(auth[7:],**data)
        except SessionDenied:
            return reply("401 Unauthorized",{"error":"invalid_session"})
        except (AccessDenied,MembershipDenied):
            return reply("403 Forbidden",{"error":"access_denied"})
        except RevisionConflict:
            return reply("409 Conflict",{"error":"revision_conflict"})
        except UpdateRequired:
            return reply("426 Upgrade Required",{"error":"update_required"})
        except (ValueError,UnicodeError,RecursionError):
            return reply("400 Bad Request",{"error":"invalid_request"})
        except Exception:
            return reply("503 Service Unavailable",{"error":"unavailable"})
        return reply("200 OK",result)
