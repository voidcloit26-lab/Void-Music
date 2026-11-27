"""Offline signing of an APK-verified stable policy. Never publishes anything."""
import argparse
import json
from pathlib import Path
import time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import ReleasePolicy, verify_policy
from guardian.release_prepare import prepare


def sign_verified(payload, key, *, apk, aapt, apksigner, expected_signer, now):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 4096:
        raise ValueError("Invalid unsigned policy")
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("Release signing requires a P-256 key")
    policy = ReleasePolicy(**json.loads(payload.decode("ascii"))).validate(now)
    if policy.canonical() != payload:
        raise ValueError("Policy is not canonical")
    checked = prepare(apk, aapt=aapt, apksigner=apksigner,
                      expected_signer=expected_signer, sequence=policy.sequence,
                      minimum=policy.minimum, now=now, expires_at=policy.expires_at)
    # Preserve the previously approved issuance time; all APK metadata must match.
    from dataclasses import replace
    if replace(checked, issued_at=policy.issued_at) != policy:
        raise ValueError("Policy does not match verified APK")
    signature = key.sign(payload, ec.ECDSA(hashes.SHA256()))
    verify_policy(payload, signature, key.public_key(), now)
    return signature


def main():
    import getpass
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("policy", "apk", "aapt", "apksigner", "key", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-signer", required=True)
    args = parser.parse_args()
    with args.policy.open("rb") as stream:
        payload = stream.read(4097)
    # Only an encrypted, locally held release-policy key is accepted.
    password = getpass.getpass("Release policy key passphrase: ").encode()
    if not password:
        parser.error("An encrypted private key is required")
    key = serialization.load_pem_private_key(args.key.read_bytes(), password=password)
    signature = sign_verified(payload, key, apk=args.apk, aapt=args.aapt,
                              apksigner=args.apksigner, expected_signer=args.expected_signer,
                              now=int(time.time()))
    with args.output.open("xb") as stream:
        stream.write(signature)
    print("APK verified; detached policy signature created. Nothing published.")


if __name__ == "__main__":
    main()
