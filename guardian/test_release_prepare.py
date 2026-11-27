import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from guardian.release_prepare import apk_digest, inspect_reports, prepare

class ReleasePrepareTests(unittest.TestCase):
    signer = "a" * 64
    badging = "package: name='online.voidbot.music' versionCode='74' versionName='1.0.0'\n"
    signature = "Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate SHA-256 digest: " + signer + "\n"

    def test_stable_report(self):
        self.assertEqual(inspect_reports(self.badging, self.signature, self.signer), (74, "1.0.0"))

    def test_invalid_report(self):
        for badging, sig, pin in [
            (self.badging.replace("online.voidbot.music", "online.voidbot.music.fast"), self.signature, self.signer),
            (self.badging + "application-debuggable\n", self.signature, self.signer),
            (self.badging.replace("1.0.0", "1.0.0 build#1"), self.signature, self.signer),
            (self.badging, self.signature.replace("true", "false"), self.signer),
            (self.badging, self.signature, "b" * 64),
            (self.badging, self.signature + "Signer #2 certificate SHA-256 digest: " + self.signer + "\n", self.signer),
            (self.badging, self.signature, ""),
        ]:
            with self.subTest(badging=badging, sig=sig, pin=pin), self.assertRaises(ValueError):
                inspect_reports(badging, sig, pin)

    def test_digest_and_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.apk"
            path.write_bytes(b"abc")
            self.assertEqual(apk_digest(path), (3, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))
            path.write_bytes(b"")
            with self.assertRaises(ValueError):
                apk_digest(path)

    def test_prepare_from_verified_reports(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.apk"
            path.write_bytes(b"abc")
            with patch("guardian.release_prepare.subprocess.run", side_effect=[
                CompletedProcess([], 0, self.badging, ""),
                CompletedProcess([], 0, self.signature, ""),
            ]):
                policy = prepare(path, aapt="aapt", apksigner="apksigner",
                                 expected_signer=self.signer, sequence=1, minimum=73,
                                 now=1700000000, expires_at=1700003600)
            self.assertEqual(policy.latest, 74)
            self.assertEqual(policy.apk_bytes, 3)
            self.assertEqual(policy.decision(73), "available")
            self.assertEqual(policy.decision(72), "required")

if __name__ == "__main__":
    unittest.main()
