"""Local owner-only management CLI; run under the dedicated Guardian service account.

No network listener. OS permissions/SSH authorization protect the management surface.
The server-side pepper must be provided by the service environment, not the APK.
"""
import argparse
import json
import os
import pathlib
import stat
import sys

from guardian.access_store import AccessStore, AccessDenied

def store_from_environment():
    os.umask(0o077)
    database_url = os.environ.get("VOID_GUARDIAN_DATABASE_URL")
    root = pathlib.Path(os.environ.get("VOID_GUARDIAN_STATE", "/tmp/void-guardian-state"))
    if not root.is_absolute():
        raise ValueError("VOID_GUARDIAN_STATE must be absolute")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if root.is_symlink() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Guardian state directory must be owned by this user with mode 0700")
    path = root / "access.sqlite"
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("Unsafe Guardian database permissions")
    pepper_file = os.environ.get("VOID_GUARDIAN_PEPPER_FILE")
    if pepper_file and "VOID_GUARDIAN_PEPPER" in os.environ:
        raise ValueError("Configure only one pepper source")
    if pepper_file:
        secret = pathlib.Path(pepper_file)
        if not secret.is_absolute():
            raise ValueError("Pepper path must be absolute")
        fd = os.open(secret, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise PermissionError("Pepper file must be an owner-only regular file (0600)")
            raw = stream.read(257)
            if len(raw) > 256:
                raise ValueError("Pepper file too long")
        pepper = bytes.fromhex(raw.decode("ascii").strip())
    else:
        pepper = bytes.fromhex(os.environ["VOID_GUARDIAN_PEPPER"])
    if database_url:
        from guardian.postgres_store import PostgresAccessStore
        return PostgresAccessStore(database_url, pepper)
    if "VOID_GUARDIAN_STATE" not in os.environ:
        raise ValueError("SQLite requires explicit persistent VOID_GUARDIAN_STATE")
    return AccessStore(str(path), pepper)

def main():
    p = argparse.ArgumentParser(description="VOID Guardian local owner console")
    sub = p.add_subparsers(dest="action", required=True)
    generate = sub.add_parser("generate")
    generate.add_argument("--uses", type=int, default=1)
    generate.add_argument("--ttl", type=int, default=86400, help="seconds; 0 means no redemption expiry")
    sub.add_parser("invitations")
    sub.add_parser("activations")
    sub.add_parser("cleanup")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("id", help="hashed invitation identifier from invitations")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("account_id")
    args = p.parse_args()
    store = store_from_environment()
    if args.action == "generate":
        print(store.generate(args.uses, None if args.ttl == 0 else args.ttl))
    elif args.action == "invitations":
        print(json.dumps(store.list_invitations(), indent=2))
    elif args.action == "activations":
        print(json.dumps(store.list_activations(), indent=2))
    elif args.action == "cleanup":
        print(store.cleanup())
    elif args.action == "cancel":
        print("cancelled" if store.cancel_id(args.id) else "not found")
    elif args.action == "revoke":
        print("revoked" if store.revoke(args.account_id) else "not found or already revoked")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, PermissionError, KeyError, AccessDenied) as exc:
        print("Guardian operation rejected: " + str(exc), file=sys.stderr)
        sys.exit(1)
