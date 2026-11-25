import io
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from guardian.access_store import AccessStore
from guardian.managed_owner import OwnerApplication, password_hash, SESSION_SECONDS

class ManagedOwnerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=AccessStore(str(Path(tmp.name)/"test.sqlite"),b"p"*32)
        self.password="test-only-guardian-password"
        self.email="owner@gmail.com"
        self.now=1000
        salt=b"s"*32
        self.app=OwnerApplication(self.store,"owner.example.test",self.email,salt.hex(),password_hash(self.password,salt).hex(),clock=lambda:self.now)
        self.cookie=""
    def call(self,path="/",data=None,auth=True,origin="https://owner.example.test",host="owner.example.test"):
        raw=b"" if data is None else urlencode(data).encode()
        env={"PATH_INFO":path,"QUERY_STRING":"","REQUEST_METHOD":"GET" if data is None else "POST","HTTP_HOST":host,"HTTP_ORIGIN":origin,"CONTENT_TYPE":"application/x-www-form-urlencoded","CONTENT_LENGTH":str(len(raw)),"wsgi.input":io.BytesIO(raw),"HTTP_COOKIE":self.cookie if auth else ""}
        result=[]
        body=b"".join(self.app(env,lambda status,headers:result.append((status,dict(headers)))))
        return result[0][0],result[0][1],body
    def login(self):
        status,headers,_=self.call("/login",{"email":self.email,"password":self.password},auth=False)
        self.assertEqual(status,"303 See Other")
        for flag in ("Secure","HttpOnly","SameSite=Strict","Path=/"):
            self.assertIn(flag,headers["Set-Cookie"])
        self.cookie=headers["Set-Cookie"].split(";")[0]
        return re.search(rb'name="csrf" value="([^"]+)"',self.call()[2]).group(1).decode()
    def test_single_owner_and_session(self):
        self.assertNotIn(b"Generate unique code",self.call()[2])
        self.assertEqual(self.call("/v1/redeem")[0],"404 Not Found")
        self.assertEqual(self.call("/healthz")[0],"200 OK")
        self.assertEqual(self.call(host="evil.test")[0],"403 Forbidden")
        self.assertEqual(self.call("/login",{"email":"other@gmail.com","password":self.password})[0],"401 Unauthorized")
        self.assertEqual(self.call("/login",{"email":self.email,"password":"wrong"})[0],"401 Unauthorized")
        csrf=self.login()
        self.assertIn(b"Generate unique code",self.call()[2])
        self.assertEqual(self.call()[1]["Cache-Control"],"no-store")
        self.assertEqual(self.call("/logout",{"csrf":csrf})[0],"303 See Other")
        self.assertNotIn(b"Generate unique code",self.call()[2])
    def test_expiration_and_origin(self):
        self.assertEqual(self.call("/login",{"email":self.email,"password":self.password},origin="https://evil.test")[0],"403 Forbidden")
        csrf=self.login()
        self.now+=SESSION_SECONDS+1
        self.assertEqual(self.call(data={"action":"generate","uses":"1","ttl":"0","csrf":csrf})[0],"401 Unauthorized")
    def test_actions(self):
        csrf=self.login()
        f={"action":"generate","uses":"2","ttl":"3600","csrf":csrf}
        self.assertEqual(self.call(data=f,origin="https://evil.test")[0],"403 Forbidden")
        self.assertEqual(self.call(data=dict(f,csrf="bad"))[0],"403 Forbidden")
        self.assertEqual(self.call(data=dict(f,uses="1001"))[0],"400 Bad Request")
        with self.assertLogs("guardian.owner.audit",level="INFO") as logs:
            status,_,body=self.call(data=f)
        self.assertEqual(status,"200 OK")
        code=re.search(rb"VOID-(?:[A-F0-9]{8}-){3}[A-F0-9]{8}",body).group()
        self.assertNotIn(code.decode()," ".join(logs.output))
        self.assertNotIn(code,self.call()[2])
        self.store.redeem(code.decode(),"12345678901234567890","a"*64)
        row=self.store.list_invitations()[0]
        self.assertEqual(self.call(data={"action":"cancel","id":row["id"],"csrf":csrf})[0],"200 OK")
        self.assertEqual(self.call(data={"action":"revoke","id":"12345678901234567890","csrf":csrf})[0],"200 OK")
        self.assertFalse(self.store.is_active("12345678901234567890","a"*64))
    def test_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.call("/login",{"email":self.email,"password":"wrong"})[0],"401 Unauthorized")
        self.assertEqual(self.call("/login",{"email":self.email,"password":self.password})[0],"429 Too Many Requests")
