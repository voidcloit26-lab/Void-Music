"""Sandbox signed release registry, independent of live Guardian and APK hosting."""
from contextlib import closing, contextmanager
import sqlite3
import time
from guardian.release_policy import ReleasePolicy, verify_policy
import json

class ReleaseRegistry:
    def __init__(self, path, public_key, *, sandbox=False, clock=time.time):
        if sandbox is not True:
            raise PermissionError('sandbox only')
        self.path, self.public_key, self.clock = path, public_key, clock
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS releases_v2 (sequence INTEGER PRIMARY KEY, payload BLOB NOT NULL, signature BLOB NOT NULL, published_at INTEGER NOT NULL)')

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def publish(self, payload, signature):
        """Accept only independently signed policies; adapter must authenticate owner."""
        with self._transaction() as db:
            now = int(self.clock())
            candidate = verify_policy(payload, signature, self.public_key, now)
            row = db.execute('SELECT sequence,payload FROM releases_v2 ORDER BY sequence DESC LIMIT 1').fetchone()
            if row:
                if candidate.sequence < row[0]:
                    raise ValueError('stale policy')
                if candidate.sequence == row[0]:
                    if row[1] != payload:
                        raise ValueError('sequence reuse')
                    return False
                previous = ReleasePolicy(**json.loads(row[1].decode("ascii")))
                if candidate.latest < previous.latest:
                    raise ValueError("latest version rollback")
                if candidate.minimum < previous.minimum:
                    raise ValueError("minimum version rollback")
                if candidate.signer_sha256 != previous.signer_sha256:
                    raise ValueError("APK signing identity changed")
                if candidate.latest == previous.latest and (
                    candidate.apk_sha256 != previous.apk_sha256 or
                    candidate.apk_bytes != previous.apk_bytes or
                    candidate.version_name != previous.version_name
                ):
                    raise ValueError("different APK for existing version")
            db.execute('INSERT INTO releases_v2 VALUES (?,?,?,?)', (candidate.sequence,payload,signature,now))
            return True

    def current(self):
        with self._transaction() as db:
            row = db.execute('SELECT payload,signature FROM releases_v2 ORDER BY sequence DESC LIMIT 1').fetchone()
            if not row:
                return None
            # Never fall back to an earlier sequence, even if current is expired.
            verify_policy(*row, self.public_key, int(self.clock()))
            return row
