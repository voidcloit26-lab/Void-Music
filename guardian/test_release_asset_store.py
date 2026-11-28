"""Offline tests for private durable APK storage; never contact GitHub."""
import hashlib
import io
import json
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError

from guardian.release_asset_store import PrivateReleaseAssets
from guardian.release_download import DownloadUnavailable


class Response(io.BytesIO):
    def __init__(self, data, *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.digest = hashlib.sha256(payload).hexdigest()
        self.private = True
        self.draft = False
        self.bad_digest = False
        self.binary = payload
        self.redirect = None
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        url = request.full_url
        if url.endswith("/repos/" + PrivateReleaseAssets.REPO):
            return Response(json.dumps({"full_name": PrivateReleaseAssets.REPO, "private": self.private}).encode())
        if "/releases/tags/" in url:
            return Response(json.dumps({
                "tag_name": "void-stable-" + self.digest,
                "draft": self.draft,
                "assets": [{
                    "name": self.digest + ".apk", "id": 42, "state": "uploaded",
                    "size": len(self.payload),
                    "digest": "sha256:" + ("0" * 64 if self.bad_digest else self.digest),
                }],
            }).encode())
        if "/releases/assets/42" in url and self.redirect:
            raise HTTPError(url, 302, "redirect", {"Location": self.redirect}, io.BytesIO())
        if "/releases/assets/42" in url or url.startswith("https://release-assets.githubusercontent.com/"):
            return Response(self.binary)
        raise AssertionError("unexpected request")


class PrivateReleaseAssetsTests(unittest.TestCase):
    def setUp(self):
        self.payload = b"synthetic apk fixture, not a real apk"
        self.opener = FakeOpener(self.payload)
        self.policy = SimpleNamespace(apk_sha256=self.opener.digest, apk_bytes=len(self.payload))
        self.token = "github_pat_" + "a" * 40

    def store(self):
        return PrivateReleaseAssets(self.token, opener=self.opener)

    def test_valid_private_asset(self):
        with self.store().open_verified(self.policy) as f:
            self.assertEqual(f.read(), self.payload)

    def test_public_repo_rejected(self):
        self.opener.private = False
        with self.assertRaises(DownloadUnavailable):
            self.store()

    def test_repo_visibility_rechecked(self):
        store = self.store()
        self.opener.private = False
        with self.assertRaises(DownloadUnavailable):
            store.open_verified(self.policy)

    def test_metadata_mismatch(self):
        self.opener.bad_digest = True
        with self.assertRaises(DownloadUnavailable):
            self.store().open_verified(self.policy)

    def test_draft_denied(self):
        self.opener.draft = True
        with self.assertRaises(DownloadUnavailable):
            self.store().open_verified(self.policy)

    def test_truncated_or_tampered_asset(self):
        for binary in (b"x", b"x" * len(self.payload), self.payload + b"x"):
            self.opener.binary = binary
            with self.assertRaises(DownloadUnavailable):
                self.store().open_verified(self.policy)

    def test_trusted_redirect_omits_token(self):
        self.opener.redirect = "https://release-assets.githubusercontent.com/private?signature=example"
        with self.store().open_verified(self.policy) as f:
            self.assertEqual(f.read(), self.payload)
        self.assertIsNone(self.opener.requests[-1].get_header("Authorization"))
        self.assertIsNotNone(self.opener.requests[-2].get_header("Authorization"))

    def test_untrusted_redirect_denied(self):
        for url in (
            "http://release-assets.githubusercontent.com/a",
            "https://release-assets.githubusercontent.com.evil.test/a",
            "https://user@release-assets.githubusercontent.com/a",
            "https://release-assets.githubusercontent.com:444/a",
        ):
            self.opener.redirect = url
            with self.assertRaises(DownloadUnavailable):
                self.store().open_verified(self.policy)
            self.assertTrue(self.opener.requests[-1].full_url.startswith("https://api.github.com/"))

    def test_token_shape_rejected(self):
        with self.assertRaises(ValueError):
            PrivateReleaseAssets("wrong-token", opener=self.opener)
