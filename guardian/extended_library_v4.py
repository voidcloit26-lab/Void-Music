"""Account-scoped extended metadata, independent of the V2 library revision.

Only a trusted device-proof adapter may call this store. No audio, paths,
credentials, provider account identifiers, or automatic history collection.
"""
import json
import re
from guardian.cloud_store import RevisionConflict
from guardian.membership_rules import MembershipDenied

ALBUM = re.compile(r"MPREb[A-Za-z0-9_-]{1,64}")
ARTIST = re.compile(r"UC[A-Za-z0-9_-]{22}")
SONG = re.compile(r"[A-Za-z0-9_-]{11}")
MAX_BYTES = 512 * 1024
EMPTY = {"albums": [], "artists": [], "history": None}
DDL = """CREATE TABLE IF NOT EXISTS extended_library_v4 (
    account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
    revision BIGINT NOT NULL CHECK(revision > 0),
    payload TEXT NOT NULL, updated_at BIGINT NOT NULL
)"""

def normalize_extended(data):
    if not isinstance(data, dict) or set(data) != {"albums", "artists", "history"}:
        raise ValueError("invalid extended library")
    def identifiers(values, pattern):
        if not isinstance(values, list) or len(values) > 1000:
            raise ValueError("invalid identifier list")
        if any(not isinstance(v, str) or not pattern.fullmatch(v) for v in values):
            raise ValueError("invalid public identifier")
        if len(set(values)) != len(values):
            raise ValueError("duplicate identifier")
        return sorted(values)
    albums = identifiers(data["albums"], ALBUM)
    artists = identifiers(data["artists"], ARTIST)
    history = data["history"]
    if history is not None:
        if not isinstance(history, list) or len(history) > 5000:
            raise ValueError("invalid listening history")
        seen = set()
        for item in history:
            if not isinstance(item, dict) or set(item) != {"song_id", "timestamp_ms", "played_ms"}:
                raise ValueError("invalid play")
            song, timestamp, played = item["song_id"], item["timestamp_ms"], item["played_ms"]
            if (not isinstance(song, str) or not SONG.fullmatch(song)
                or type(timestamp) is not int or not 1 <= timestamp <= 253402300799999
                or type(played) is not int or not 1 <= played <= 86400000):
                raise ValueError("invalid play")
            key = (timestamp, song, played)
            if key in seen:
                raise ValueError("duplicate play")
            seen.add(key)
        history = [{"song_id": song, "timestamp_ms": ts, "played_ms": ms}
                   for ts, song, ms in sorted(seen)]
    payload = json.dumps({"albums": albums, "artists": artists, "history": history},
                         ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload) > MAX_BYTES:
        raise ValueError("extended library too large")
    return payload

class ExtendedLibraryStore:
    def __init__(self, identity):
        self.identity = identity

    def read(self, account, device):
        store = self.identity
        with store.transaction() as db:
            store._require_device(db, store._account(account), store._device(device))
            row = db.execute("SELECT revision,payload FROM extended_library_v4 WHERE account=?", (account,)).fetchone()
            return (row[0], json.loads(row[1])) if row else (0, None)

    def _replace(self, account, device, expected, data, *, clearing=False, history_only=False):
        if type(expected) is not int or not 0 <= expected < 2**63-1:
            raise ValueError("invalid revision")
        payload = normalize_extended(data)
        store = self.identity
        with store.transaction() as db:
            store._require_device(db, store._account(account), store._device(device))
            now = store._now()
            if not clearing:
                member = store._membership(db, account)
                if member is None or member.status(now) != "active":
                    raise MembershipDenied("active membership required")
            row = db.execute("SELECT revision,payload FROM extended_library_v4 WHERE account=?", (account,)).fetchone()
            revision = row[0] if row else 0
            if expected != revision:
                raise RevisionConflict("review extended library before saving")
            if history_only:
                current = json.loads(row[1]) if row else dict(EMPTY)
                current["history"] = None
                payload = normalize_extended(current)
            elif not clearing and row and data["history"] is None:
                # Opting out of history collection must not silently remove
                # previously saved history when albums/artists are updated.
                current = json.loads(payload)
                current["history"] = json.loads(row[1])["history"]
                payload = normalize_extended(current)
            if not clearing and row and row[1] == payload:
                return revision
            db.execute("""INSERT INTO extended_library_v4 (account,revision,payload,updated_at)
                VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET revision=excluded.revision,
                payload=excluded.payload,updated_at=excluded.updated_at""", (account, revision+1, payload, now))
            return revision+1

    def write(self, account, device, expected, data):
        return self._replace(account, device, expected, data)

    def clear(self, account, device, expected):
        # Preserve a revisioned empty snapshot; old clients cannot revive data.
        return self._replace(account, device, expected, EMPTY, clearing=True)

    def clear_history(self, account, device, expected):
        # Clear listening history separately, even after membership expires.
        return self._replace(account, device, expected, EMPTY, clearing=True, history_only=True)


def verify_stage(store):
    """Require the migration and least-privilege runtime grants before enabling."""
    table = "guardian_v2_stage.extended_library_v4"
    with store.transaction() as db:
        db.execute("SELECT account,revision,payload,updated_at FROM extended_library_v4 LIMIT 0")
        for privilege in ("SELECT", "INSERT", "DELETE", "TRUNCATE", "UPDATE", "TRIGGER"):
            allowed = db.execute("SELECT has_table_privilege(current_user,?,?)",
                                 (table, privilege)).fetchone()[0]
            if allowed != (privilege in ("SELECT", "INSERT")):
                raise PermissionError("invalid extended library table grants")
        for column in ("account", "revision", "payload", "updated_at"):
            allowed = db.execute("SELECT has_column_privilege(current_user,?,?,'UPDATE')",
                                 (table, column)).fetchone()[0]
            if allowed != (column != "account"):
                raise PermissionError("invalid extended library column grants")
