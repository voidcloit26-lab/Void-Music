"""Signed-policy gate for future stable lease issuance.

The version and certificate are device-proof-bound claims, NOT hardware
attestation. A modified client can lie; independent attestation is required
for tamper-resistant version enforcement. Never enable before stable delivery.
"""
import re
from guardian.release_policy import verify_policy


class UpdateRequired(ValueError):
    pass


class VersionGate:
    def __init__(self, registry):
        self.registry = registry

    def require_supported(self, version, signer):
        if type(version) is not int or not 1 <= version <= 2100000000:
            raise ValueError("invalid installed version")
        if not isinstance(signer, str) or not re.fullmatch(r"[a-f0-9]{64}", signer):
            raise ValueError("invalid installed signer")
        release = self.registry.current()
        if release is None:
            raise RuntimeError("release policy unavailable")
        policy = verify_policy(*release, self.registry.public_key, int(self.registry.clock()))
        if version < policy.minimum or version > policy.latest or signer != policy.signer_sha256:
            raise UpdateRequired("unsupported release")
        return policy
