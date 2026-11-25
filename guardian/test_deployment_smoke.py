"""Exercise the real HTTP boundary and persistent state across service recreation."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.activation_api import create_app
from guardian.bootstrap import initialize
from guardian.device_protocol import b64, unb64, proof_message, read_device_key, device_account
from guardian.owner_cli import store_from_environment

class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass

class DeploymentSmokeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "state"
        public = initialize(self.root)
        self.signer = serialization.load_der_public_key(unb64(public))
        env = patch.dict(os.environ, {"VOID_GUARDIAN_STATE": str(self.root),
                    "VOID_GUARDIAN_PEPPER_FILE": str(self.root / "pepper.hex")}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.store = store_from_environment()
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public = b64(self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        _, self.fingerprint = read_device_key(self.public)
        self.server = None
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        self.server = make_server("127.0.0.1", 0, create_app(), handler_class=Quiet)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            self.server = None

    def call(self, path, data):
        req = urllib.request.Request(self.base + path, json.dumps(data).encode(),
                                     {"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def proof(self, action, code=""):
        status, obj = self.call("/v1/challenge", {"public_key": self.public, "action": action})
        self.assertEqual(status, 200)
        nonce = obj["nonce"]
        result = {"public_key": self.public, "nonce": nonce,
                  "signature": b64(self.key.sign(proof_message(nonce, self.fingerprint, action, code),
                                                ec.ECDSA(hashes.SHA256())))}
        if action == "redeem": result["code"] = code
        return result

    def verify(self, receipt):
        data = unb64(receipt["payload"])
        self.signer.verify(unb64(receipt["signature"]), data, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(json.loads(data)["device"], self.fingerprint)

    def test_redeem_restart_revoke(self):
        code = self.store.generate()
        status, receipt = self.call("/v1/redeem", self.proof("redeem", code))
        self.assertEqual(status, 200)
        self.verify(receipt)
        self.assertEqual(self.store.list_invitations(), [])
        stale = self.proof("status")
        self.stop()
        self.start()
        self.assertEqual(self.call("/v1/status", stale)[0], 403)
        status, receipt = self.call("/v1/status", self.proof("status"))
        self.assertEqual(status, 200)
        self.verify(receipt)
        self.assertTrue(self.store.revoke(device_account(self.fingerprint)))
        self.assertEqual(self.call("/v1/status", self.proof("status")), (403, {"error":"access_inactive"}))

    def test_owner_routes_not_exposed(self):
        self.assertEqual(self.call("/owner", {})[0], 404)
        self.assertEqual(self.call("/v1/generate", {})[0], 404)
