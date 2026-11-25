import unittest
from unittest.mock import patch
from guardian.owner_provision import create_app

class OwnerProvisionTests(unittest.TestCase):
    def test_unconfigured_denies_every_route(self):
        with patch.dict("os.environ",{},clear=True), patch("guardian.owner_provision.configured_app") as configured:
            app=create_app()
            for path in ("/","/login","/healthz","/v1/redeem"):
                result=[]
                body=b"".join(app({"PATH_INFO":path,"REQUEST_METHOD":"POST"},lambda s,h:result.append(s)))
                self.assertEqual(result,["503 Service Unavailable"])
                self.assertEqual(body,b"Guardian owner setup pending.")
            configured.assert_not_called()
    def test_configured_delegates(self):
        settings={k:"test" for k in ("VOID_GUARDIAN_OWNER_HOST","VOID_GUARDIAN_OWNER_EMAIL","VOID_GUARDIAN_DATABASE_URL","VOID_GUARDIAN_PEPPER","VOID_GUARDIAN_OWNER_PASSWORD")}
        with patch.dict("os.environ",settings,clear=True), patch("guardian.owner_provision.configured_app") as configured:
            self.assertIs(create_app(),configured.return_value)
