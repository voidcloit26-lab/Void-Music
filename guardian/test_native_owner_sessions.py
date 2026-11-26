import sqlite3
import tempfile
import unittest
from pathlib import Path
from guardian.access_store import AccessStore
from guardian.native_owner_sessions import NativeOwnerSessions, NATIVE_SESSION_SECONDS

class DurableNativeSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "state.sqlite")
        self.store = AccessStore(self.path, b"p" * 32)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE native_owner_session(slot INTEGER PRIMARY KEY CHECK(slot=1), digest BLOB NOT NULL, expires_at INTEGER NOT NULL)")
        self.now = 1000
        self.scope = b"s" * 32
        self.sessions = NativeOwnerSessions(self.store, self.scope, lambda: self.now)
        self.token = "a" * 43

    def test_restart_and_expiry(self):
        self.sessions.replace(self.token)
        second = NativeOwnerSessions(AccessStore(self.path, b"p" * 32), self.scope, lambda: self.now)
        self.assertTrue(second.valid(self.token))
        with sqlite3.connect(self.path) as db:
            self.assertNotEqual(db.execute("SELECT digest FROM native_owner_session").fetchone()[0], self.token.encode())
        self.now += NATIVE_SESSION_SECONDS
        self.assertFalse(second.valid(self.token))

    def test_replacement_logout_and_credential_change(self):
        self.sessions.replace(self.token)
        changed = NativeOwnerSessions(self.store, b"t" * 32, lambda: self.now)
        self.assertFalse(changed.valid(self.token))
        replacement = "b" * 43
        self.sessions.replace(replacement)
        self.assertFalse(self.sessions.valid(self.token))
        self.sessions.revoke(self.token)
        self.assertTrue(self.sessions.valid(replacement))
        self.sessions.revoke(replacement)
        self.assertFalse(self.sessions.valid(replacement))
        self.sessions.replace(self.token)
        self.sessions.clear()
        self.assertFalse(self.sessions.valid(self.token))

    def test_missing_migration_fails_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE native_owner_session")
        with self.assertRaises(sqlite3.OperationalError):
            NativeOwnerSessions(self.store, self.scope)

if __name__ == "__main__":
    unittest.main()
