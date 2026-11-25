import base64
import hashlib
import io
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from guardian.access_store import AccessStore
from guardian.managed_owner import OwnerApplication

class ManagedOwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=AccessStore(str(Path(self.tmp.name)/"test.sqlite"), b"p"*32)
        self.password="test-only-password"
        self.app=OwnerApplication(self.store, "owner.example.test", hashlib.sha256(self.password.encode()).hexdigest())
    def call(self, path="/", data=None, auth=True, origin="https://owner.example.test", host="owner.example.test"):
        raw=b"" if data is None else urlencode(data).encode()
        env={"PATH_INFO":path,"QUERY_STRING":"","REQUEST_METHOD":"GET" if data is None else "POST",
             "HTTP_HOST":host,"HTTP_ORIGIN":origin,"CONTENT_TYPE":"application/x-www-form-urlencoded",
             "CONTENT_LENGTH":str(len(raw)),"wsgi.input":io.BytesIO(raw)}
        if auth:
            env["HTTP_AUTHORIZATION"]="Basic "+base64.b64encode(("owner:"+self.password).encode()).decode()
        result=[]
        body=b"".join(self.app(env,lambda status,headers:result.append((status,dict(headers)))))
        return result[0][0], result[0][1], body
    def test_isolation_and_auth(self):
        self.assertEqual(self.call(auth=False)[0],"401 Unauthorized")
        self.assertEqual(self.call("/v1/redeem")[0],"404 Not Found")
        self.assertEqual(self.call("/healthz",auth=False)[0],"200 OK")
        self.assertEqual(self.call(host="evil.test")[0],"403 Forbidden")
        status,headers,body=self.call()
        self.assertEqual(status,"200 OK")
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertEqual(headers["X-Frame-Options"],"DENY")
    def test_generate_cancel_and_revoke(self):
        fields={"action":"generate","uses":"2","ttl":"3600","csrf":self.app.csrf}
        self.assertEqual(self.call(data=fields,origin="https://evil.test")[0],"403 Forbidden")
        self.assertEqual(self.call(data=dict(fields,csrf="bad"))[0],"403 Forbidden")
        self.assertEqual(self.store.list_invitations(),[])
        with self.assertLogs("guardian.owner.audit",level="INFO") as logs:
            status,headers,body=self.call(data=fields)
        self.assertEqual(status,"200 OK")
        code=re.search(rb"VOID-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}",body).group()
        self.assertNotIn(code.decode()," ".join(logs.output))
        self.assertNotIn(code,self.call()[2])
        self.store.redeem(code.decode(),"12345678901234567890","a"*64)
        row=self.store.list_invitations()[0]
        self.assertEqual(row["remaining"],1)
        self.assertEqual(self.call(data={"action":"cancel","id":row["id"],"csrf":self.app.csrf})[0],"200 OK")
        self.assertEqual(self.store.list_invitations(),[])
        self.assertEqual(self.call(data={"action":"revoke","id":"12345678901234567890","csrf":self.app.csrf})[0],"200 OK")
        self.assertFalse(self.store.is_active("12345678901234567890","a"*64))
    def test_invalid_bounds_and_failed_auth_budget(self):
        self.assertEqual(self.call(data={"action":"generate","uses":"1001","ttl":"0","csrf":self.app.csrf})[0],"400 Bad Request")
        for _ in range(30):
            self.assertEqual(self.call(auth=False)[0],"401 Unauthorized")
        self.assertEqual(self.call(auth=False)[0],"429 Too Many Requests")
