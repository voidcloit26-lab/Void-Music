import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.access_store import AccessStore, AccessDenied
from guardian.device_protocol import DeviceProtocol, b64, unb64, proof_message, device_account

class DeviceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AccessStore(str(Path(self.tmp.name) / "state.sqlite"), b"x"*32)
        self.server = ec.generate_private_key(ec.SECP256R1())
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.now = 100
        self.protocol = DeviceProtocol(self.store, self.server, clock=lambda: self.now)
        self.der = self.device.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.public = b64(self.der)
        self.fingerprint = hashlib.sha256(self.der).hexdigest()
    def request(self, action, code=""):
        nonce = self.protocol.challenge(self.public, action)["nonce"]
        signature = b64(self.device.sign(proof_message(nonce, self.fingerprint, action, code), ec.ECDSA(hashes.SHA256())))
        return self.public, nonce, signature
    def test_redeem_lifetime_and_signature(self):
        code = self.store.generate()
        result = self.protocol.redeem(*self.request("redeem", code), code)
        payload = unb64(result["payload"])
        self.server.public_key().verify(unb64(result["signature"]), payload, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(json.loads(payload)["device"], self.fingerprint)
        self.assertEqual(self.store.list_invitations(), [])
        self.assertIn("payload", self.protocol.status(*self.request("status")))
    def test_replay_and_revocation(self):
        code = self.store.generate()
        args = self.request("redeem", code)
        self.protocol.redeem(*args, code)
        with self.assertRaises(AccessDenied): self.protocol.redeem(*args, code)
        self.store.revoke(device_account(self.fingerprint))
        with self.assertRaises(AccessDenied): self.protocol.status(*self.request("status"))
    def test_expiry_and_code_binding(self):
        code = self.store.generate()
        args = self.request("redeem", code)
        self.now += 121
        with self.assertRaises(AccessDenied): self.protocol.redeem(*args, code)
        args = self.request("redeem", code)
        another = self.store.generate()
        with self.assertRaises(AccessDenied): self.protocol.redeem(*args, another)
        self.assertEqual(len(self.store.list_invitations()), 2)
    def test_wrong_key(self):
        code = self.store.generate()
        public, nonce, _ = self.request("redeem", code)
        wrong = ec.generate_private_key(ec.SECP256R1())
        sig = b64(wrong.sign(proof_message(nonce, self.fingerprint, "redeem", code), ec.ECDSA(hashes.SHA256())))
        with self.assertRaises(AccessDenied): self.protocol.redeem(public, nonce, sig, code)
        self.assertEqual(len(self.store.list_invitations()),1)

if __name__ == "__main__":
    unittest.main()
