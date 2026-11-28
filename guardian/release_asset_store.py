"""Private GitHub release assets, verified into a bounded temporary file.

The upstream token is server-only and is never sent to the asset CDN or client.
No automatic redirects, public repositories, unverified artifacts or fallback URLs.
"""
import hashlib
import hmac
import json
import re
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from guardian.release_download import DownloadUnavailable


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrivateReleaseAssets:
    API = "https://api.github.com"
    CDN = frozenset(("release-assets.githubusercontent.com", "objects.githubusercontent.com"))
    REPO = "voidcloit26-lab/void-music-private-releases"

    def __init__(self, token, *, opener=None):
        if not isinstance(token, str) or not re.fullmatch(r"github_pat_[A-Za-z0-9_]{20,512}", token):
            raise ValueError("repository-scoped read-only token required")
        self._token = token
        self._opener = opener or build_opener(NoRedirect())
        self._require_private()

    def _request(self, path, accept):
        return Request(self.API + path, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": accept,
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "VOID-Guardian-Release/2",
            "Accept-Encoding": "identity",
        })

    def _json(self, path):
        try:
            with self._opener.open(self._request(path, "application/vnd.github+json"), timeout=10) as response:
                if response.status != 200:
                    raise DownloadUnavailable("release metadata unavailable")
                data = response.read(262145)
                if len(data) > 262144:
                    raise DownloadUnavailable("release metadata too large")
                return json.loads(data)
        except Exception:
            raise DownloadUnavailable("release metadata unavailable") from None

    def _require_private(self):
        info = self._json("/repos/" + self.REPO)
        if not isinstance(info, dict) or info.get("full_name", "").lower() != self.REPO or info.get("private") is not True:
            raise DownloadUnavailable("private release repository required")

    def _open_asset(self, asset_id):
        req = self._request("/repos/" + self.REPO + "/releases/assets/" + str(asset_id),
                            "application/octet-stream")
        try:
            return self._opener.open(req, timeout=15)
        except HTTPError as exc:
            try:
                if exc.code != 302:
                    raise DownloadUnavailable("release asset unavailable")
                location = exc.headers.get("Location", "")
                url = urlsplit(location)
                if (url.scheme != "https" or url.hostname not in self.CDN or url.port not in (None, 443)
                        or url.username is not None or url.password is not None or url.fragment):
                    raise DownloadUnavailable("untrusted release redirect")
            finally:
                exc.close()
        # Never forward the GitHub token or cookies to the CDN.
        return self._opener.open(Request(location, headers={
            "Accept": "application/octet-stream", "Accept-Encoding": "identity",
            "User-Agent": "VOID-Guardian-Release/2"}), timeout=15)

    def open_verified(self, policy):
        digest = policy.apk_sha256
        size = policy.apk_bytes
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise DownloadUnavailable("invalid signed release hash")
        if type(size) is not int or not 1 <= size <= 500 * 1024 * 1024:
            raise DownloadUnavailable("invalid signed release size")
        output = None
        try:
            self._require_private()
            tag = "void-stable-" + digest
            release = self._json("/repos/" + self.REPO + "/releases/tags/" + tag)
            if not isinstance(release, dict) or release.get("tag_name") != tag or release.get("draft") is not False:
                raise DownloadUnavailable("release is not published")
            assets = release.get("assets")
            if not isinstance(assets, list):
                raise DownloadUnavailable("release assets unavailable")
            matches = [a for a in assets if isinstance(a, dict) and a.get("name") == digest + ".apk"]
            if len(matches) != 1:
                raise DownloadUnavailable("unique release asset required")
            asset = matches[0]
            asset_id = asset.get("id")
            if (type(asset_id) is not int or asset_id <= 0 or asset.get("state") != "uploaded"
                    or type(asset.get("size")) is not int or asset["size"] != size
                    or asset.get("digest") != "sha256:" + digest):
                raise DownloadUnavailable("release asset metadata mismatch")
            output = tempfile.TemporaryFile(mode="w+b")
            deadline = time.monotonic() + 120
            check = hashlib.sha256()
            remaining = size
            with self._open_asset(asset_id) as response:
                if response.status != 200 or response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise DownloadUnavailable("invalid asset response")
                length = response.headers.get("Content-Length")
                if length is not None and length != str(size):
                    raise DownloadUnavailable("asset length mismatch")
                while remaining:
                    if time.monotonic() > deadline:
                        raise DownloadUnavailable("asset transfer timeout")
                    block = response.read(min(1024 * 1024, remaining))
                    if not block or len(block) > remaining:
                        raise DownloadUnavailable("truncated or oversized asset")
                    output.write(block)
                    check.update(block)
                    remaining -= len(block)
                if response.read(1) or not hmac.compare_digest(check.hexdigest(), digest):
                    raise DownloadUnavailable("asset hash mismatch")
            output.seek(0)
            return output
        except Exception:
            if output is not None:
                output.close()
            # Do not propagate provider URLs, signed query strings or credentials.
            raise DownloadUnavailable("verified private release unavailable") from None
