import io
import json
import os
import unittest
from unittest.mock import patch
from guardian.business_stage_entry import create_app, REQUIRED


class BusinessStageEntryTests(unittest.TestCase):
    def call(self, app, path="/healthz", method="GET", query=""):
        response = {}
        def start(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)
        body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": method,
                             "QUERY_STRING": query, "wsgi.input": io.BytesIO(b"")}, start))
        return response, json.loads(body)

    def test_default_is_locked(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
        response, body = self.call(app)
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        self.assertEqual(body["mode"], "business-readiness-only")
        self.assertIs(body["owner_routes_enabled"], False)
        self.assertIs(body["payments_enabled"], False)

    def test_locked_owner_routes_and_methods(self):
        with patch.dict(os.environ, {"VOID_V2_UNIFIED_BUSINESS_ENABLED": "false"}, clear=True):
            app = create_app()
        for route in ("/owner/v2/summary", "/owner/v2/codes/create", "/owner/v2/price"):
            with self.subTest(route=route):
                self.assertEqual(self.call(app, route, "POST")[0]["status"], "404 Not Found")
        self.assertEqual(self.call(app, method="POST")[0]["status"], "405 Method Not Allowed")
        self.assertEqual(self.call(app, query="x=1")[0]["status"], "404 Not Found")

    def test_incomplete_or_invalid_configuration_fails_closed(self):
        for env in ({"VOID_V2_UNIFIED_BUSINESS_ENABLED": "yes"},
                    {"VOID_V2_UNIFIED_BUSINESS_ENABLED": "true"}):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError):
                    create_app()

    def test_explicit_complete_configuration_delegates(self):
        env = {name: "test-placeholder" for name in REQUIRED}
        env["VOID_V2_UNIFIED_BUSINESS_ENABLED"] = "true"
        with patch.dict(os.environ, env, clear=True), patch("guardian.unified_business_stage.create_app") as factory:
            self.assertIs(create_app(), factory.return_value)
            factory.assert_called_once_with()

if __name__ == "__main__":
    unittest.main()
