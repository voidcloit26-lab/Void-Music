import unittest
from guardian import test_account_protocol_v2 as fixture_module
from guardian.cloud_store import RevisionConflict
from guardian.membership_rules import MembershipDenied


class UpgradeBackupTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture_module.ProtocolTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.f.call("redeem_free", {"code": self.f.store.issue_free(self.f.account, "lifetime")})
        self.library = {"favorites": ["track"], "playlists": [], "preferences": {}}

    def save(self, revision=0, library=None):
        return self.f.call("backup_for_upgrade", {"revision": revision, "library": self.library if library is None else library})

    def test_backup_and_recovery(self):
        result = self.save()
        self.assertEqual(result["revision"], 1)
        self.assertEqual(self.f.call("cloud_read", {})["library"], self.library)
        with self.assertRaises(MembershipDenied):
            self.f.store.recover_linked(fixture_module.ISSUER, "user_a", self.f.recovery, self.f.other_fp)
        with self.assertRaises(MembershipDenied):
            self.f.store.recover_linked(fixture_module.ISSUER, "user_b", result["recovery"], self.f.other_fp)
        account, next_code = self.f.store.recover_linked(fixture_module.ISSUER, "user_a", result["recovery"], self.f.other_fp)
        self.assertEqual(account, self.f.account)
        self.assertNotEqual(next_code, result["recovery"])
        self.assertEqual(self.f.store.read_library(account, self.f.other_fp)[1], self.library)
        with self.assertRaises(MembershipDenied):
            self.f.store.recover_linked(fixture_module.ISSUER, "user_a", result["recovery"], self.f.fp)

    def test_stale_revision_preserves_code_and_backup(self):
        result = self.save()
        with self.assertRaises(RevisionConflict):
            self.save(0)
        self.assertEqual(self.f.call("cloud_read", {})["revision"], 1)
        self.f.store.recover_linked(fixture_module.ISSUER, "user_a", result["recovery"], self.f.other_fp)

    def test_conflict_does_not_delete_library(self):
        result = self.save()
        with self.assertRaises(RevisionConflict):
            self.save(1, {"favorites": [], "playlists": [], "preferences": {}})
        self.assertEqual(self.f.call("cloud_read", {})["library"], self.library)
        self.f.store.recover_linked(fixture_module.ISSUER, "user_a", result["recovery"], self.f.other_fp)

    def test_identical_backup_rotates_only_recovery(self):
        first = self.save()
        second = self.save(1)
        self.assertEqual(second["revision"], 1)
        self.assertNotEqual(first["recovery"], second["recovery"])
        with self.assertRaises(MembershipDenied):
            self.f.store.recover_linked(fixture_module.ISSUER, "user_a", first["recovery"], self.f.other_fp)
        self.f.store.recover_linked(fixture_module.ISSUER, "user_a", second["recovery"], self.f.other_fp)

    def test_wrong_device_and_suspended_denied(self):
        with self.assertRaises(MembershipDenied):
            self.f.store.backup_for_upgrade(self.f.account, self.f.other_fp, 0, self.library)
        self.f.store.set_state(self.f.account, "suspended")
        with self.assertRaises(MembershipDenied):
            self.save()
        self.assertEqual(self.f.call("cloud_read", {})["revision"], 0)
