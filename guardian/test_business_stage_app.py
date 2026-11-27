import io
import json
import unittest
from guardian.business_stage_app import BusinessApplication
from guardian.business_store import BusinessDenied

class Fake:
    def login(self, owner, password):
        if (owner,password)!=("test","synthetic"):
            raise BusinessDenied("denied")
        return "a"*43
    def verify(self, token):
        if token!="a"*43: raise BusinessDenied("denied")
    def logout(self, token): return True

class AppTests(unittest.TestCase):
    def setUp(self):
        self.app=BusinessApplication(Fake(), lambda e,s: (s("404 Not Found",[]),[b"{}"])[1])
    def request(self,path,data=None,method="POST",**extra):
        raw=json.dumps(data or {}).encode()
        env=dict(PATH_INFO=path,REQUEST_METHOD=method,CONTENT_TYPE="application/json",
                 CONTENT_LENGTH=str(len(raw)), **{"wsgi.input":io.BytesIO(raw)},**extra)
        result=[]
        body=b"".join(self.app(env,lambda status,headers:result.append(status)))
        return result[0],json.loads(body)
    def test_login_and_logout(self):
        status,result=self.request("/owner/v2/login",{"owner":"test","password":"synthetic"})
        self.assertEqual(status,"200 OK")
        self.assertEqual(result["expires_in"],300)
        self.assertEqual(self.request("/owner/v2/logout",HTTP_AUTHORIZATION="Bearer "+result["token"])[0],"200 OK")
    def test_denied_login(self):
        self.assertEqual(self.request("/owner/v2/login",{"owner":"test","password":"wrong"})[0],"401 Unauthorized")
    def test_customer_token_denied(self):
        self.assertEqual(self.request("/owner/v2/logout",HTTP_AUTHORIZATION="Bearer x.y.z")[0],"401 Unauthorized")
    def test_browser_denied(self):
        self.assertEqual(self.request("/owner/v2/login",HTTP_ORIGIN="https://example.test")[0],"403 Forbidden")
        self.assertEqual(self.request("/owner/v2/login",HTTP_COOKIE="x=y")[0],"403 Forbidden")
    def test_no_customer_routes(self):
        self.assertEqual(self.request("/v2/execute")[0],"404 Not Found")
    def test_health_and_method(self):
        self.assertEqual(self.request("/healthz",method="GET")[1]["payments_enabled"],False)
        self.assertEqual(self.request("/owner/v2/login",method="GET")[0],"405 Method Not Allowed")

if __name__=="__main__":
    unittest.main()
