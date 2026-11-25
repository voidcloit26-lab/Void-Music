"""Initialize persistent secrets for an independent Guardian installation.

Run once under the dedicated service user. Never print or overwrite a secret.
If state is partial or existing files are unsafe, fail and require manual recovery.
"""
import os
import pathlib
import secrets
import stat
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.device_protocol import b64

def safe_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise PermissionError("Unsafe secret file")
        data = file.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Secret file too large")
        return data

def create_exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())

def initialize(root):
    root = pathlib.Path(root)
    if not root.is_absolute():
        raise ValueError("State path must be absolute")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Unsafe state directory")
    pepper, signing = root / "pepper.hex", root / "signing-key.pem"
    present = [p.exists() or p.is_symlink() for p in (pepper, signing)]
    if not any(present):
        if any(root.iterdir()):
            raise ValueError("Nonempty state without secrets; recover the originals")
        key = ec.generate_private_key(ec.SECP256R1())
        create_exclusive(signing, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        create_exclusive(pepper, secrets.token_hex(32).encode("ascii") + b"\n")
    elif not all(present):
        raise ValueError("Partial state; recover original secrets before continuing")
    raw = safe_read(pepper, 256)
    if len(bytes.fromhex(raw.decode("ascii").strip())) < 32:
        raise ValueError("Invalid pepper")
    key = serialization.load_pem_private_key(safe_read(signing, 8192), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("P-256 signing key required")
    return b64(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))

if __name__ == "__main__":
    os.umask(0o077)
    # Public key only, never secret material. Preserve it across backups/restores.
    print("VOID_GUARDIAN_PUBLIC_KEY=" + initialize(os.environ["VOID_GUARDIAN_STATE"]))
