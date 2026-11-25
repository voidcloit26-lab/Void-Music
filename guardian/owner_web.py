"""Local-only VOID Guardian owner console. Run interactively over trusted SSH.

This is a development console, not a public HTTPS admin service. Never publish
its port through a reverse proxy. The access store is not yet connected to APKs.
"""
import base64
import hmac
import html
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from guardian.owner_cli import store_from_environment

def esc(value):
    return html.escape(str(value), quote=True)

def page(store, csrf, message="", code=""):
    rows = "".join(
        "<tr><td>" + esc(x["remaining"]) + "</td><td>" +
        esc(x["expires_at"] or "No expiry") + "</td><td>" +
        '<form method="post"><input type="hidden" name="csrf" value="' + esc(csrf) +
        '"><input type="hidden" name="action" value="cancel"><input type="hidden" name="id" value="' +
        esc(x["id"]) + '"><button>Cancel unused code</button></form></td></tr>'
        for x in store.list_invitations()
    )
    activated = "".join(
        "<tr><td>" + esc(x["account_id"]) + "</td><td>" +
        esc("Revoked" if x["revoked_at"] else "Lifetime") + "</td><td>" +
        ("" if x["revoked_at"] else
         '<form method="post"><input type="hidden" name="csrf" value="' + esc(csrf) +
         '"><input type="hidden" name="action" value="revoke"><input type="hidden" name="id" value="' +
         esc(x["account_id"]) + '"><button>Revoke access</button></form>') + "</td></tr>"
        for x in store.list_activations()
    )
    result = ('<p role="status">' + esc(message) + '</p>') if message else ""
    if code:
        result += '<p>Copy this code now; it will not be shown again.</p><pre>' + esc(code) + '</pre>'
    return ('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VOID Guardian · Owner</title>
<style>
*{box-sizing:border-box}body{background:#101016;color:#eee;font:16px system-ui;margin:0;padding:24px}
main{max-width:850px;margin:auto}section{background:#1b1b25;border:1px solid #373344;border-radius:16px;padding:20px;margin:16px 0}
h1,h2{margin-top:0}label{display:block;margin:10px 0}input,select,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #655c78;background:#282532;color:#fff;max-width:100%}
button{cursor:pointer;background:#493673}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #373344;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#dbbaff}small{color:#b9b3c6}
</style><main><h1>VOID Guardian / Owner</h1>
<p>Private invitation management — local development only.</p>''' + result +
        '<section><h2>Generate access code</h2><form method="post"><input type="hidden" name="csrf" value="' +
        esc(csrf) + '"><input type="hidden" name="action" value="generate">' +
        '''<label>Number of users (1 = personal code)<input type="number" name="uses" min="1" max="1000" value="1" required></label>
<label>Redemption expiry <select name="ttl"><option value="3600">1 hour</option><option value="86400" selected>24 hours</option><option value="604800">7 days</option><option value="0">No expiry</option></select></label>
<p>Successful activation is lifetime, unless revoked.</p><button>Generate unique code</button></form></section>
<section><h2>Available invitations</h2><small>Expiry is shown as UTC Unix seconds. Expired and fully redeemed keys disappear.</small><table><thead><tr><th>Uses left</th><th>Expiry</th><th>Action</th></tr></thead><tbody>''' +
        (rows or '<tr><td colspan="3">No active invitations</td></tr>') +
        '</tbody></table></section><section><h2>Activated users</h2><table><thead><tr><th>Account</th><th>Status</th><th>Action</th></tr></thead><tbody>' +
        (activated or '<tr><td colspan="3">No activated users</td></tr>') + '</tbody></table></section></main></html>').encode("utf-8")

def make_handler(store, password, csrf, port):
    expected = "Basic " + base64.b64encode(("owner:" + password).encode()).decode()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def reply(self, status, content=b"", challenge=False):
            self.send_response(status)
            if challenge:
                self.send_header("WWW-Authenticate", 'Basic realm="VOID Guardian"')
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)
        def authorized(self):
            if self.headers.get("Host") not in allowed_hosts:
                self.reply(403); return False
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected.encode()):
                self.reply(401, challenge=True); return False
            return True
        def do_GET(self):
            if not self.authorized(): return
            if self.path != "/": self.reply(404); return
            self.reply(200, page(store, csrf))
        def do_POST(self):
            if not self.authorized(): return
            if self.path != "/": self.reply(404); return
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {"http://" + host for host in allowed_hosts}:
                self.reply(403); return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
                self.reply(415); return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096: raise ValueError()
                fields = parse_qs(self.rfile.read(size).decode(), strict_parsing=True, max_num_fields=10)
                if any(len(v) != 1 for v in fields.values()): raise ValueError()
                f = {k: v[0] for k, v in fields.items()}
            except (ValueError, UnicodeError):
                self.reply(400); return
            if not hmac.compare_digest(f.get("csrf", "").encode(), csrf.encode()):
                self.reply(403); return
            try:
                action = f.get("action")
                if action == "generate":
                    ttl = int(f["ttl"])
                    if ttl not in (0, 3600, 86400, 604800): raise ValueError()
                    code = store.generate(int(f["uses"]), ttl or None)
                    self.reply(200, page(store, csrf, "Invitation generated.", code)); return
                if action == "cancel":
                    msg = "Invitation cancelled." if store.cancel_id(f["id"]) else "Invitation unavailable."
                elif action == "revoke":
                    msg = "Access revoked." if store.revoke(f["id"]) else "Activation unavailable."
                else: raise ValueError()
                self.reply(200, page(store, csrf, msg))
            except (ValueError, KeyError):
                self.reply(400, b"Invalid request")
    return Handler

def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not sys.stdout.isatty():
        raise SystemExit("Run interactively; do not log owner credentials.")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Invalid port")
    store = store_from_environment()
    password, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(store, password, csrf, args.port))
    server.timeout = 1
    print(f"Local owner console: http://127.0.0.1:{args.port}/")
    print("Username: owner")
    print("Session password (do not share):", password)
    print("Stop with Ctrl+C. Remote access only through trusted SSH port forwarding.")
    try:
        while True:
            server.handle_request()
            store.cleanup()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
