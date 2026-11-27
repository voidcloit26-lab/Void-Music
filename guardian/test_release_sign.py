import unittest
from dataclasses import replace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy, verify_policy
from guardian.release_sign import sign_verified


class ReleaseSigningTests(unittest.TestCase):
    def setUp(self):
        self.now = 1700000000
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.policy = ReleasePolicy(1, 74, 73, "1.0.0", "a"*64, "b"*64,
                                    1024, self.now-10, self.now+3600)

    def sign(self, payload=None, key=None):
        return sign_verified(payload if payload is not None else self.policy.canonical(),
                             key if key is not None else self.key,
                             apk="test.apk", aapt="aapt", apksigner="apksigner",
                             expected_signer=self.policy.signer_sha256, now=self.now)

    def test_valid_verified_policy(self):
        with patch("guardian.release_sign.prepare", return_value=replace(self.policy, issued_at=self.now)):
            sig = self.sign()
        self.assertEqual(verify_policy(self.policy.canonical(), sig, self.key.public_key(), self.now), self.policy)

    def test_reject_mismatch(self):
        for field, value in [("apk_sha256", "c"*64), ("signer_sha256", "c"*64),
                             ("apk_bytes", 100), ("latest", 75), ("version_name", "1.0.1")]:
            with self.subTest(field=field), patch("guardian.release_sign.prepare", return_value=replace(self.policy, **{field: value})):
                with self.assertRaises(ValueError):
                    self.sign()

    def test_reject_noncanonical_and_wrong_curve(self):
        with self.assertRaises(ValueError):
            self.sign(payload=self.policy.canonical()+b" ")
        with self.assertRaises(ValueError):
            self.sign(key=ec.generate_private_key(ec.SECP384R1()))

    def test_reject_unverified_apk(self):
        with patch("guardian.release_sign.prepare", side_effect=ValueError("bad APK")):
            with self.assertRaises(ValueError):
                self.sign()

if __name__ == "__main__":
    unittest.main()
