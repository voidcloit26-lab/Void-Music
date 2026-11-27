"""Offline stable APK preflight. No network, private keys, or publication."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import time

from guardian.release_policy import MAX_APK_BYTES, PACKAGE, ReleasePolicy


def apk_digest(path):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > MAX_APK_BYTES:
                raise ValueError("APK exceeds release limit")
            digest.update(block)
    if size == 0:
        raise ValueError("Empty APK")
    return size, digest.hexdigest()


def inspect_reports(badging, signature, expected_signer):
    if not re.fullmatch(r"[a-f0-9]{64}", expected_signer):
        raise ValueError("Pinned permanent APK certificate required")
    lines = [line for line in badging.splitlines() if line.startswith("package:")]
    if len(lines) != 1 or any(line.startswith("application-debuggable") for line in badging.splitlines()):
        raise ValueError("Invalid or debuggable APK")
    match = re.match(r"package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'", lines[0])
    if not match or match[1] != PACKAGE:
        raise ValueError("Expected stable VOID Music application ID")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", match[3]):
        raise ValueError("Stable version name must use three numeric components")
    certs = re.findall(r"^Signer #[0-9]+ certificate SHA-256 digest: ([a-fA-F0-9]{64})\s*$", signature, re.M)
    if len(certs) != 1 or certs[0].lower() != expected_signer:
        raise ValueError("APK signing certificate does not match permanent pin")
    if not re.search(r"^Verified using v2 scheme .*: true\s*$", signature, re.M):
        raise ValueError("APK Signature Scheme v2 verification required")
    return int(match[2]), match[3]


def prepare(apk, *, aapt, apksigner, expected_signer, sequence, minimum, now, expires_at):
    apk = Path(apk).resolve(strict=True)
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        raise ValueError("Expected an APK file")
    before = apk_digest(apk)
    badging = subprocess.run([str(aapt), "dump", "badging", str(apk)], check=True,
                             capture_output=True, text=True, timeout=120).stdout
    signature = subprocess.run([str(apksigner), "verify", "--verbose", "--print-certs", str(apk)],
                               check=True, capture_output=True, text=True, timeout=120).stdout
    version, version_name = inspect_reports(badging, signature, expected_signer)
    if apk_digest(apk) != before:
        raise ValueError("APK changed during verification")
    size, digest = before
    return ReleasePolicy(sequence, version, minimum, version_name, digest, expected_signer,
                         size, now, expires_at).validate(now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--aapt", type=Path, required=True)
    parser.add_argument("--apksigner", type=Path, required=True)
    parser.add_argument("--expected-signer", required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--minimum", type=int, required=True)
    parser.add_argument("--ttl-hours", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.ttl_hours <= 168:
        parser.error("TTL must be 1 to 168 hours")
    now = int(time.time())
    policy = prepare(args.apk, aapt=args.aapt, apksigner=args.apksigner,
                     expected_signer=args.expected_signer, sequence=args.sequence,
                     minimum=args.minimum, now=now, expires_at=now+args.ttl_hours*3600)
    with args.output.open("xb") as stream:
        stream.write(policy.canonical())
    print("Verified APK and wrote UNSIGNED release policy. Nothing published.")


if __name__ == "__main__":
    main()
