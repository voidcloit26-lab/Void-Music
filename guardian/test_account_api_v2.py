import io
import json
import unittest
from guardian.account_api_v2 import AccountAPI
from guardian.clerk_session import SessionDenied
from guardian.cloud_store import RevisionConflict
from guardian.membership_rules import MembershipDenied

class FakeProtocol:
    def challenge(self,token,**data):
        if token=="bad":
            raise SessionDenied("secret")
        if token=="denied":
            raise MembershipDenied("secret")
        return {"nonce":"test"}
    def execute(self,token,**data):
        raise RevisionConflict("private")

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.api=AccountAPI(FakeProtocol(),sandbox=True)
        self.data={"public_key":"pub","action":"status","body":{}}

    def call(self,path="/v2/challenge",token="ok",raw=None,**extra):
        if raw is None:
            raw=json.dumps(self.data).encode()
        env={"PATH_INFO":path,"REQUEST_METHOD":"POST","HTTP_AUTHORIZATION":"Bearer "+token,
             "CONTENT_TYPE":"application/json","CONTENT_LENGTH":str(len(raw)),"wsgi.input":io.BytesIO(raw)}
        env.update(extra)
        result=[]
        body=b"".join(self.api(env,lambda status,headers:result.extend((status,dict(headers)))))
        return result[0],result[1],json.loads(body)

    def test_success_and_no_cache(self):
        status,headers,data=self.call()
        self.assertEqual(status,"200 OK")
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertEqual(data,{"nonce":"test"})

    def test_sandbox_and_routes(self):
        with self.assertRaises(PermissionError):
            AccountAPI(FakeProtocol())
        self.assertTrue(self.call(path="/v2/owner")[0].startswith("404"))
        self.assertTrue(self.call(REQUEST_METHOD="GET")[0].startswith("405"))

    def test_error_redaction(self):
        for token,expected in (("bad","401"),("denied","403"),("","401")):
            status,_,data=self.call(token=token)
            self.assertTrue(status.startswith(expected))
            self.assertNotIn("secret",str(data))
        raw=json.dumps({**self.data,"nonce":"n","signature":"s"}).encode()
        self.assertTrue(self.call(path="/v2/execute",raw=raw)[0].startswith("409"))

    def test_reject_malformed_and_oversize(self):
        for raw in (b'{"body":{},"body":{},"action":"status","public_key":"x"}',
                    b'{"body":{"x":NaN},"action":"status","public_key":"x"}',b'[]'):
            self.assertTrue(self.call(raw=raw)[0].startswith("400"))
        self.assertTrue(self.call(CONTENT_LENGTH="9999999")[0].startswith("413"))
        self.assertTrue(self.call(CONTENT_TYPE="text/plain")[0].startswith("415"))
