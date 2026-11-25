import base64
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from guardian.access_store import AccessStore
from guardian.owner_web import make_handler

class OwnerWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AccessStore(str(Path(self.tmp.name) / "test.sqlite"), b"p"*32)
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.store, "test-password", "test-csrf", 0))
        self.port = self.server.server_port
        self.server.RequestHandlerClass = make_handler(self.store, "test-password", "test-csrf", self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
    def close(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
    def request(self, data=None, auth=True, headers=None):
        h = dict(headers or {})
        if auth: h["Authorization"] = "Basic " + base64.b64encode(b"owner:test-password").decode()
        body = None if data is None else urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/", data=body, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=5) as r: return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
    def test_auth_required(self):
        self.assertEqual(self.request(auth=False)[0], 401)
        self.assertEqual(self.request()[0], 200)
    def test_csrf_and_origin(self):
        data = {"action":"generate","uses":"2","ttl":"3600"}
        self.assertEqual(self.request(data)[0],403)
        data["csrf"]="test-csrf"
        self.assertEqual(self.request(data, headers={"Origin":"https://evil.invalid"})[0],403)
        self.assertEqual(self.store.list_invitations(),[])
    def test_generate_one_time_display_and_cancel(self):
        data = {"action":"generate","uses":"2","ttl":"3600","csrf":"test-csrf"}
        status, text = self.request(data)
        self.assertEqual(status,200)
        code = re.search(r"VOID-(?:[A-F0-9]{8}-){3}[A-F0-9]{8}",text).group()
        self.assertNotIn(code,self.request()[1])
        rows=self.store.list_invitations()
        self.assertEqual(rows[0]["remaining"],2)
        self.assertEqual(self.request({"action":"cancel","id":rows[0]["id"],"csrf":"test-csrf"})[0],200)
        self.assertEqual(self.store.list_invitations(),[])
    def test_invalid_limit(self):
        self.assertEqual(self.request({"action":"generate","uses":"1001","ttl":"0","csrf":"test-csrf"})[0],400)

if __name__ == "__main__":
    unittest.main()
