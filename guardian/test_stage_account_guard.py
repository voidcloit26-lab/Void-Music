import unittest
from guardian.clerk_session import SessionDenied, VerifiedSession
from guardian.stage_account_guard import AccountFairness, authorize_request


class Verifier:
    def verify(self, token):
        if token not in ("a", "b", "a-new"):
            raise SessionDenied("invalid")
        return VerifiedSession("https://example.test", "user_a" if token.startswith("a") else "user_b", "sess_"+token)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.limit = AccountFairness(limit=2, capacity=2, clock=lambda: self.now)

    def request(self, token):
        return authorize_request({"HTTP_AUTHORIZATION": "Bearer "+token}, Verifier(), self.limit)

    def test_invalid_does_not_allocate(self):
        for token in ("", "bad", "x"*8193):
            self.assertTrue(self.request(token)[0].startswith("401"))
        self.assertEqual(self.limit.entries, {})

    def test_sessions_share_account_quota(self):
        self.assertIsNone(self.request("a"))
        self.assertIsNone(self.request("a-new"))
        self.assertTrue(self.request("a")[0].startswith("429"))
        self.assertIsNone(self.request("b"))

    def test_window_expires(self):
        self.request("a")
        self.request("a")
        self.now += 60
        self.assertIsNone(self.request("a"))

    def test_capacity_no_active_eviction(self):
        self.assertTrue(self.limit.take("first"))
        self.assertTrue(self.limit.take("second"))
        self.assertFalse(self.limit.take("third"))
        self.assertIn("first", self.limit.entries)

    def test_backward_clock(self):
        self.request("a")
        self.now -= 1
        self.assertTrue(self.request("a")[0].startswith("429"))

    def test_verifier_unavailable(self):
        class Broken:
            def verify(self, token):
                raise RuntimeError("internal")
        result = authorize_request({"HTTP_AUTHORIZATION":"Bearer a"}, Broken(), self.limit)
        self.assertEqual(result, ("503 Service Unavailable", {"error":"unavailable"}))


if __name__ == "__main__":
    unittest.main()
