"""Read-only managed staging release policy registry.

The customer runtime may read signed policies but cannot publish or change
them. Publishing requires offline APK verification, an independent signature
and a separate trusted deployment operator. No private signing key here.
"""
import time
from cryptography.hazmat.primitives.asymmetric import ec
from guardian.release_policy import verify_policy


class ReleaseUnavailable(RuntimeError):
    pass


class StageReleaseRegistry:
    def __init__(self, store, public_key, *, clock=time.time):
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
            raise ValueError("independent release public key required")
        self.store, self.public_key, self.clock = store, public_key, clock
        with store.transaction() as db:
            db.execute("SELECT sequence,payload,signature FROM releases_v2 LIMIT 0")
            table = "guardian_v2_stage.releases_v2"
            if not db.execute("SELECT has_table_privilege(current_user,?,'SELECT')", (table,)).fetchone()[0]:
                raise PermissionError("release policy read grant missing")
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                if db.execute("SELECT has_table_privilege(current_user,?,?)", (table, privilege)).fetchone()[0]:
                    raise PermissionError("release registry must be read-only")

    def current(self):
        try:
            with self.store.transaction() as db:
                row = db.execute("SELECT sequence,payload,signature FROM releases_v2 ORDER BY sequence DESC LIMIT 1").fetchone()
                if not row:
                    return None
                sequence, payload, signature = row
                payload, signature = bytes(payload), bytes(signature)
                policy = verify_policy(payload, signature, self.public_key, int(self.clock()))
                if sequence != policy.sequence:
                    raise ValueError("signed sequence mismatch")
                return payload, signature
        except Exception as exc:
            raise ReleaseUnavailable("release policy unavailable") from exc
