import unittest
from datetime import datetime, timezone
from guardian.membership_rules import Membership, MembershipDenied, grant, annual_end, validate_manual_payment

def ts(y,m,d):
    return int(datetime(y,m,d,tzinfo=timezone.utc).timestamp())

class MembershipRulesTests(unittest.TestCase):
    now = ts(2026,11,26)

    def test_annual_boundary(self):
        p = grant(None, "annual", self.now)
        self.assertEqual(p.expires_at, ts(2027,11,26))
        self.assertEqual(p.status(p.expires_at-1), "active")
        self.assertEqual(p.status(p.expires_at), "expired")
        self.assertEqual(p.lease_until(p.expires_at-10), p.expires_at)
        with self.assertRaises(MembershipDenied):
            p.lease_until(p.expires_at)

    def test_early_and_late_renewal(self):
        p = grant(None,"annual",self.now)
        self.assertEqual(grant(p,"renewal",self.now).expires_at,ts(2028,11,26))
        self.assertEqual(grant(p,"renewal",ts(2028,1,1)).expires_at,ts(2029,1,1))

    def test_lifetime_and_trial(self):
        p = grant(None,"lifetime",self.now)
        self.assertIsNone(p.expires_at)
        self.assertEqual(p.status(ts(2050,1,1)), "active")
        self.assertEqual(p.lease_until(self.now), self.now+86400)
        with self.assertRaises(MembershipDenied):
            grant(p,"renewal",self.now)
        trial = grant(None,"trial",self.now,days=7)
        self.assertEqual(trial.expires_at,self.now+7*86400)

    def test_suspension_cannot_be_bypassed(self):
        for state in ("revoked","suspended"):
            p=Membership("annual",ts(2027,11,26),state)
            self.assertEqual(p.status(self.now),state)
            for kind in ("annual","renewal","lifetime"):
                with self.assertRaises(MembershipDenied):
                    grant(p,kind,self.now)

    def test_leap_day(self):
        self.assertEqual(annual_end(ts(2028,2,29)),ts(2029,2,28))

    def test_bad_grants(self):
        with self.assertRaises(MembershipDenied):
            grant(None,"renewal",self.now)
        with self.assertRaises(MembershipDenied):
            grant(grant(None,"annual",self.now),"annual",self.now)
        with self.assertRaises(ValueError):
            grant(None,"trial",self.now,days=True)
        with self.assertRaises(ValueError):
            grant(None,"lifetime",self.now,days=365)

    def test_payment_validation_only(self):
        self.assertEqual(validate_manual_payment(500,"USD","example-chain","a"*64),("example-chain","a"*64))
        for amount,currency,network,ref in [(0,"USD","example-chain","a"*64),(500,"INR","example-chain","a"*64),(True,"USD","example-chain","a"*64),(500,"USD","bad network","a"*64),(500,"USD","example-chain","short")]:
            with self.assertRaises(ValueError):
                validate_manual_payment(amount,currency,network,ref)
