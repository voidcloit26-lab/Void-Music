"""Isolated membership rules; trusted server-side callers only.
No HTTP routes, wallet operations or live database changes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import calendar
import re

class MembershipDenied(ValueError):
    pass

@dataclass(frozen=True)
class Membership:
    kind: str
    expires_at: int | None
    state: str = "enabled"

    def __post_init__(self):
        if self.kind not in ("annual", "lifetime", "trial", "complimentary"):
            raise ValueError("invalid membership kind")
        if self.state not in ("enabled", "suspended", "revoked"):
            raise ValueError("invalid membership state")
        if self.kind == "lifetime":
            if self.expires_at is not None:
                raise ValueError("lifetime has no expiry")
        elif type(self.expires_at) is not int or self.expires_at <= 0:
            raise ValueError("fixed term requires expiry")

    def status(self, now):
        if type(now) is not int or now <= 0:
            raise ValueError("invalid server time")
        if self.state != "enabled":
            return self.state
        if self.expires_at is not None and now >= self.expires_at:
            return "expired"
        return "active"

    def lease_until(self, now, max_seconds=86400):
        if self.status(now) != "active":
            raise MembershipDenied("inactive")
        if type(max_seconds) is not int or not 1 <= max_seconds <= 86400:
            raise ValueError("invalid offline lease limit")
        return min(now + max_seconds, self.expires_at) if self.expires_at is not None else now + max_seconds

def annual_end(start):
    """One calendar year in UTC; Feb 29 maps to Feb 28."""
    if type(start) is not int or start <= 0:
        raise ValueError("invalid server time")
    date = datetime.fromtimestamp(start, timezone.utc)
    day = min(date.day, calendar.monthrange(date.year + 1, date.month)[1])
    return int(date.replace(year=date.year + 1, day=day).timestamp())

def grant(existing, kind, now, *, days=None):
    """Pure transition; caller authenticates account, owner, and invitation.
    Persist atomically with redemption and payment consumption.
    """
    if type(now) is not int or now <= 0:
        raise ValueError("invalid server time")
    if existing is not None and existing.state != "enabled":
        raise MembershipDenied("owner must resolve suspension or revocation")
    if existing is not None and existing.kind == "lifetime":
        raise MembershipDenied("lifetime already granted")
    if kind in ("annual", "renewal"):
        if days is not None:
            raise ValueError("annual duration is fixed")
        if kind == "annual" and existing is not None:
            raise MembershipDenied("existing member requires renewal")
        if kind == "renewal" and existing is None:
            raise MembershipDenied("renewal requires an existing account membership")
        base = max(now, existing.expires_at) if existing is not None else now
        return Membership("annual", annual_end(base))
    if kind == "lifetime":
        if days is not None:
            raise ValueError("lifetime duration is not configurable")
        return Membership("lifetime", None)
    if kind in ("trial", "complimentary"):
        if existing is not None:
            raise MembershipDenied("cannot overwrite existing membership")
        if type(days) is not int or not 1 <= days <= 365:
            raise ValueError("invalid duration")
        return Membership(kind, now + days * 86400)
    raise ValueError("invalid invitation type")

def validate_manual_payment(price_cents, quoted_currency, network, reference):
    """Structural check only; does NOT verify chain settlement or authorize payment.
    Settlement evidence and unique network/reference constraints belong to the store.
    """
    if type(price_cents) is not int or not 1 <= price_cents <= 1000000:
        raise ValueError("invalid quoted price")
    if quoted_currency != "USD":
        raise ValueError("USD quote required")
    if not isinstance(network, str) or not re.fullmatch(r"[a-z0-9-]{2,32}", network):
        raise ValueError("invalid network")
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9:_-]{16,128}", reference):
        raise ValueError("invalid transaction reference")
    return (network, reference)
