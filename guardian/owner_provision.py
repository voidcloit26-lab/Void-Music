"""Fail-closed owner provisioning entrypoint, separate from activation API."""
import os
from guardian.managed_owner import create_app as configured_app

def create_app():
    required = ("VOID_GUARDIAN_OWNER_HOST", "VOID_GUARDIAN_OWNER_EMAIL",
                "VOID_GUARDIAN_DATABASE_URL", "VOID_GUARDIAN_PEPPER")
    password_ready = bool(os.environ.get("VOID_GUARDIAN_OWNER_PASSWORD") or
        (os.environ.get("VOID_GUARDIAN_OWNER_PASSWORD_SALT") and
         os.environ.get("VOID_GUARDIAN_OWNER_PASSWORD_SCRYPT")))
    if all(os.environ.get(key) for key in required) and password_ready:
        return configured_app()
    # No database access, authentication, setup form, or public setup endpoint.
    def unavailable(env, start):
        body = b"Guardian owner setup pending."
        start("503 Service Unavailable", [
            ("Content-Type","text/plain; charset=utf-8"),
            ("Content-Length",str(len(body))),
            ("Cache-Control","no-store"),
            ("X-Content-Type-Options","nosniff"),
        ])
        return [body]
    return unavailable
