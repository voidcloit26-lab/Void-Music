"""Transaction-backed global request budget for one isolated Guardian service.

The database schema must be provisioned separately. The runtime role cannot
create tables. An upstream per-client limit is still required for fairness.
"""
import time

DDL = """CREATE TABLE IF NOT EXISTS request_budget_v2 (
    bucket TEXT PRIMARY KEY, window_start BIGINT NOT NULL,
    used INTEGER NOT NULL CHECK(used>0)
);"""


class SharedBudget:
    def __init__(self, store, *, bucket, limit=120, clock=time.time):
        if bucket not in ('account', 'owner', 'release-download'):
            raise ValueError('invalid budget bucket')
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError('invalid budget capacity')
        self.store, self.bucket, self.limit, self.clock = store, bucket, limit, clock
        with store.transaction() as db:
            db.execute('SELECT bucket,window_start,used FROM request_budget_v2 LIMIT 0')

    def take(self):
        # Fail closed on DB errors or backward wall-clock movement. The shared
        # store serializes these transactions across workers. At most three rows.
        with self.store.transaction() as db:
            now = int(self.clock())
            if now <= 0:
                return False
            row = db.execute('SELECT window_start,used FROM request_budget_v2 WHERE bucket=?',
                             (self.bucket,)).fetchone()
            if row is None or now >= row[0] + 60:
                db.execute('INSERT INTO request_budget_v2 VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET window_start=excluded.window_start,used=1',
                           (self.bucket,now))
                return True
            if now < row[0] or row[1] >= self.limit:
                return False
            db.execute('UPDATE request_budget_v2 SET used=used+1 WHERE bucket=?', (self.bucket,))
            return True
