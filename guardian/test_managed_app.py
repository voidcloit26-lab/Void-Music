import base64
import io
import json
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.device_protocol import b64
from guardian.managed_app import config, create_app, ManagedApplication

class ManagedAppTests(unittest.TestCase):
    def setUp(self):
        key = ec.generate_private_key(ec.SECP256R1())
        self.env = {
            "VOID_GUARDIAN_DATABASE_URL": "postgresql://guardian:ci-only@db.example/guardian?sslmode=verify-full",
            "VOID_GUARDIAN_PEPPER": "a0"*32,
            "VOID_GUARDIAN_SIGNING_KEY_B64": base64.b64encode(key.private_bytes(
                serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode("ascii"),
            "VOID_GUARDIAN_PUBLIC_KEY": b64(key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)),
        }

    def test_requires_all_settings_and_no_local_state(self):
        for name in self.env:
            invalid = dict(self.env)
            del invalid[name]
            with self.assertRaises(ValueError):
                config(invalid)
        with self.assertRaises(ValueError):
            config(dict(self.env, VOID_GUARDIAN_STATE="/tmp/unsafe"))
        with self.assertRaises(ValueError):
            config(dict(self.env, VOID_GUARDIAN_PEPPER_FILE="/tmp/unsafe"))
        self.assertEqual(config(self.env)[1], bytes.fromhex("a0"*32))

    def test_reject_key_mismatch_and_short_pepper(self):
        with self.assertRaises(ValueError):
            config(dict(self.env, VOID_GUARDIAN_PUBLIC_KEY="different"))
        with self.assertRaises(ValueError):
            config(dict(self.env, VOID_GUARDIAN_PEPPER="aa"))

    def test_database_failure_never_falls_back_or_exposes_secret(self):
        with patch.dict("os.environ", self.env, clear=True):
            with patch("guardian.managed_app.PostgresAccessStore", side_effect=RuntimeError("sensitive")):
                with self.assertRaisesRegex(RuntimeError, "^Guardian database initialization failed;"):
                    create_app()

    def test_startup_fingerprint_only(self):
        import hashlib
        public_der = base64.urlsafe_b64decode(self.env["VOID_GUARDIAN_PUBLIC_KEY"] + "=" * (-len(self.env["VOID_GUARDIAN_PUBLIC_KEY"]) % 4))
        with patch.dict("os.environ", self.env, clear=True):
            with patch("guardian.managed_app.PostgresAccessStore"):
                with self.assertLogs("gunicorn.error", level="INFO") as logs:
                    create_app()
        self.assertIn(hashlib.sha256(public_der).hexdigest(), " ".join(logs.output))
        self.assertNotIn(self.env["VOID_GUARDIAN_SIGNING_KEY_B64"], " ".join(logs.output))
        self.assertNotIn(self.env["VOID_GUARDIAN_PEPPER"], " ".join(logs.output))

    def test_readiness_has_no_owner_routes_or_secret_data(self):
        def fake_api(env, start):
            start("404 Not Found", [])
            return [b"{}"]
        app = ManagedApplication(fake_api)
        def call(path, method="GET", query=""):
            status = []
            response = app({"PATH_INFO":path, "REQUEST_METHOD":method, "QUERY_STRING":query,
                            "wsgi.input":io.BytesIO(b"")}, lambda s,h:status.append(s))
            return status[0], json.loads(b"".join(response))
        self.assertEqual(call("/healthz"), ("200 OK", {"status":"ready"}))
        self.assertEqual(call("/healthz", "POST")[0], "405 Method Not Allowed")
        self.assertEqual(call("/healthz", query="x=1")[0], "404 Not Found")
        self.assertEqual(call("/owner")[0], "404 Not Found")

    def test_diagnostics_do_not_include_secret(self):
        import psycopg
        from guardian.managed_app import database_failure_category
        self.assertEqual(database_failure_category(psycopg.OperationalError("root certificate missing SECRET")), "tls_ca_missing")
        self.assertEqual(database_failure_category(psycopg.OperationalError("password authentication failed SECRET")), "authentication")
        self.assertEqual(database_failure_category(RuntimeError("SECRET")), "unexpected")
        self.assertEqual(database_failure_category(PermissionError("SECRET")), "runtime_grants")

    def test_managed_tls_uses_explicit_bundle_and_rejects_weak_mode(self):
        import certifi
        from pathlib import Path
        from guardian.postgres_store import PostgresAccessStore
        url = "postgresql://guardian_runtime:ci-only@db.example/void_guardian?sslmode=verify-full&sslrootcert=system"
        with patch("guardian.access_store.AccessStore.__init__", return_value=None):
            store = PostgresAccessStore(url, b"p"*32, initialize_schema=False)
            self.assertEqual(store.tls_options["sslrootcert"], certifi.where())
            self.assertTrue(Path(certifi.where()).is_file())
            with self.assertRaises(ValueError):
                PostgresAccessStore(url.replace("verify-full", "require"), b"p"*32, initialize_schema=False)

    def test_safe_tls_diagnostic_subcategories(self):
        import psycopg
        from guardian.managed_app import database_failure_category
        self.assertEqual(database_failure_category(psycopg.OperationalError("certificate verify failed SECRET")), "tls_chain")
        self.assertEqual(database_failure_category(psycopg.OperationalError("server certificate does not match host SECRET")), "tls_hostname")
