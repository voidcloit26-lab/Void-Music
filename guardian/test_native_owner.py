import io
import json
import tempfile
import unittest
from pathlib import Path
from guardian.access_store import AccessStore
from guardian.managed_owner import OwnerApplication, password_hash, SESSION_SECONDS

class NativeOwnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = AccessStore(str(Path(tmp.name)/"test.sqlite"), b"p"*32)
        self.password = "test-only-guardian-password"
        salt = b"s"*32
        self.now = 1000
        self.app = OwnerApplication(self.store, "owner.example.test", "owner@gmail.com",
            salt.hex(), password_hash(self.password,salt).hex(), clock=lambda:self.now)
    def call(self, path, data=None, token="", origin="", cookie=""):
        raw = json.dumps(data if data is not None else {}).encode()
        env = {"PATH_INFO":"/native/v1/"+path,"QUERY_STRING":"","REQUEST_METHOD":"POST",
            "HTTP_HOST":"owner.example.test","HTTP_ORIGIN":origin,
            "CONTENT_TYPE":"application/json","CONTENT_LENGTH":str(len(raw)),
            "wsgi.input":io.BytesIO(raw),"HTTP_AUTHORIZATION":"Bearer "+token if token else "", "HTTP_COOKIE":cookie}
        result=[]
        obj=json.loads(b"".join(self.app(env,lambda status,headers:result.append((status,dict(headers))))))
        return int(result[0][0].split()[0]), obj
    def login(self):
        status, obj = self.call("login", {"email":"owner@gmail.com","password":self.password})
        self.assertEqual(status, 200)
        return obj["token"]
    def test_actions(self):
        self.assertEqual(self.call("list")[0],401)
        self.assertEqual(self.call("login", {"email":"owner@gmail.com","password":self.password},origin="https://evil.example")[0],403)
        token=self.login()
        self.assertEqual(self.call("list",token=token)[1]["invitations"],[])
        self.assertEqual(self.call("generate",{"uses":True,"ttl":3600},token)[0],400)
        code=self.call("generate",{"uses":2,"ttl":3600},token)[1]["code"]
        self.store.redeem(code,"12345678901234567890","a"*64)
        data=self.call("list",token=token)[1]
        self.assertNotIn(code,json.dumps(data))
        self.assertNotIn("device_fingerprint",data["devices"][0])
        self.assertTrue(self.call("cancel",{"id":data["invitations"][0]["id"]},token)[1]["ok"])
        self.assertTrue(self.call("revoke",{"id":data["devices"][0]["account_id"]},token)[1]["ok"])
        self.assertFalse(self.store.is_active("12345678901234567890","a"*64))
        self.assertEqual(self.call("logout",token=token)[0],200)
        self.assertEqual(self.call("list",token=token)[0],401)
    def test_sessions(self):
        first=self.login()
        second=self.login()
        self.assertEqual(self.call("list",token=first)[0],401)
        self.assertEqual(self.call("list",token=second,origin="https://evil.example")[0],403)
        self.now+=SESSION_SECONDS+1
        self.assertEqual(self.call("list",token=second)[0],401)
    def test_credentials(self):
        for _ in range(5):
            self.assertEqual(self.call("login",{"email":"owner@gmail.com","password":"wrong"})[0],401)
        self.assertEqual(self.call("login",{"email":"owner@gmail.com","password":self.password})[0],429)
