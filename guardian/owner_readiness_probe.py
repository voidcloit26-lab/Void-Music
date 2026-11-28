"""One-time staging diagnostic: no account creation, no credential logging."""
import logging
from guardian.clerk_session import VerifiedSession


def check_owner_profile(policy, profile_lookup):
    logger = logging.getLogger(__name__)
    # A probe is not a user session and must not grant or issue an entitlement.
    # Limit to configured identities; report only the aggregate outcome.
    if len(policy.owners) != 1:
        logger.warning("Owner profile readiness: exactly one owner required for probe")
        return False
    subject = next(iter(policy.owners))
    try:
        profile = profile_lookup(subject)
        policy.authorize(VerifiedSession(policy.issuer, subject, "sess_probe"), profile)
    except Exception as exc:
        logger.warning("Owner profile readiness: denied (%s)", type(exc).__name__)
        return False
    logger.info("Owner profile readiness: verified")
    return True
