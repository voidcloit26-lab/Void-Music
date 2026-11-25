"""Run locally in a trusted terminal; no network, never enter Google password."""
import getpass
import secrets
from guardian.managed_owner import password_hash, EMAIL

def main():
    email=input("Owner Gmail address: ").strip().lower()
    if not EMAIL.fullmatch(email):
        raise SystemExit("Invalid Gmail address")
    password=getpass.getpass("New unique Guardian password (not Google password): ")
    if len(password)<16 or len(password)>256 or password!=getpass.getpass("Confirm Guardian password: "):
        raise SystemExit("Passwords must match and contain 16–256 characters")
    salt=secrets.token_bytes(32)
    print("Set these values directly in the private Render environment; do not share them:")
    print("VOID_GUARDIAN_OWNER_EMAIL="+email)
    print("VOID_GUARDIAN_OWNER_PASSWORD_SALT="+salt.hex())
    print("VOID_GUARDIAN_OWNER_PASSWORD_SCRYPT="+password_hash(password,salt).hex())

if __name__=="__main__":
    main()
