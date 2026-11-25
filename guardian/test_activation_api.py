import io
import json
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.access_store import AccessStore
from guardian.device_protocol import DeviceProtocol, b64, unb64, proof_message, read_device_key, device_account
from guardian.activation_api import ActivationAPI, RequestBudget

class ActivationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = AccessStore(str(Path(self.temp.name) / "db.sqlite"), b"x" * 32)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.signer = ec.generate_private_key(ec.SECP256R1())
        self.public = b64(self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        _, self.fingerprint = read_device_key(self.public)
        self.app = ActivationAPI(DeviceProtocol(self.store, self.signer))

    def call(self, path, data=None, *, raw=None, method="POST", media="application/json", length=None, query=""):
        body = json.dumps(data).encode() if raw is None else raw
        status = []
        headers = []
        env = {"PATH_INFO": path, "QUERY_STRING": query, "REQUEST_METHOD": method, "CONTENT_TYPE": media,
               "CONTENT_LENGTH": str(len(body)) if length is None else length, "wsgi.input": io.BytesIO(body)}
        def start(s, h):
            status.append(s)
            headers.extend(h)
        result = json.loads(b"".join(self.app(env, start)))
        self.assertIn(("Cache-Control", "no-store"), headers)
        return int(status[0].split()[0]), result

    def proof(self, action, code=""):
        status, response = self.call("/v1/challenge", {"public_key": self.public, "action": action})
        self.assertEqual(status, 200)
        nonce = response["nonce"]
        return {"public_key": self.public, "nonce": nonce, "signature": b64(self.key.sign(
            proof_message(nonce, self.fingerprint, action, code), ec.ECDSA(hashes.SHA256())))}

    def test_lifetime_redeem_status_and_revocation(self):
        code = self.store.generate()
        proof = dict(self.proof("redeem", code), code=code)
        status, result = self.call("/v1/redeem", proof)
        self.assertEqual(status, 200)
        self.signer.public_key().verify(unb64(result["signature"]), unb64(result["payload"]), ec.ECDSA(hashes.SHA256()))
        self.assertEqual(self.call("/v1/redeem", proof)[0], 403)
        self.assertEqual(self.call("/v1/status", self.proof("status"))[0], 200)
        self.store.revoke(device_account(self.fingerprint))
        self.assertEqual(self.call("/v1/status", self.proof("status")), (403, {"error": "access_inactive"}))

    def test_bad_proof_is_not_revocation(self):
        proof = self.proof("status")
        proof["signature"] = "AAAA"
        self.assertEqual(self.call("/v1/status", proof), (403, {"error": "access_denied"}))

    def test_input_restrictions(self):
        self.assertEqual(self.call("/owner", {})[0], 404)
        self.assertEqual(self.call("/v1/status", {}, method="GET")[0], 405)
        self.assertEqual(self.call("/v1/status", {}, query="code=secret")[0], 404)
        self.assertEqual(self.call("/v1/status", {}, media="text/plain")[0], 415)
        self.assertEqual(self.call("/v1/status", raw=b"x"*4097)[0], 413)
        self.assertEqual(self.call("/v1/status", raw=b"{", length="3")[0], 400)
        self.assertEqual(self.call("/v1/status", raw=b'{"public_key":"x","public_key":"y"}')[0], 400)
        self.assertEqual(self.call("/v1/status", raw=b"[]")[0], 400)

    def test_rate_limit_is_bounded(self):
        clock = [100]
        self.app.budget = RequestBudget(limit=2, window=60, clock=lambda: clock[0])
        self.assertEqual(self.call("/v1/status", {})[0], 400)
        self.assertEqual(self.call("/v1/status", {})[0], 400)
        self.assertEqual(self.call("/v1/status", {})[0], 429)
        self.assertEqual(len(self.app.budget.times), 2)
        clock[0] += 60
        self.assertEqual(self.call("/v1/status", {})[0], 400)

if __name__ == "__main__":
    unittest.main()
