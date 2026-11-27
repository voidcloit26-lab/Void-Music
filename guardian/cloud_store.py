"""Isolated cloud library prototype: metadata only, no audio or local file paths.

Trusted adapter must authenticate device possession before calling these methods.
Account recovery and membership changes share the identity transaction lock.
"""
from contextlib import closing
import json
import re
import sqlite3
import secrets
from guardian.identity_store import IdentityStore
from guardian.membership_rules import MembershipDenied

DDL = """CREATE TABLE IF NOT EXISTS cloud_library_v2 (
    account TEXT PRIMARY KEY REFERENCES accounts_v2(id),
    revision INTEGER NOT NULL CHECK(revision>0),
    payload TEXT NOT NULL, updated_at INTEGER NOT NULL
);"""
ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
MAX_BYTES = 512 * 1024

class RevisionConflict(ValueError):
    pass


def normalize(data):
    if not isinstance(data, dict) or set(data) != {"favorites", "playlists", "preferences"}:
        raise ValueError("invalid library fields")
    def tracks(values):
        if not isinstance(values, list) or len(values)>1000:
            raise ValueError("invalid track list")
        for value in values:
            if not isinstance(value, str) or not ID.fullmatch(value):
                raise ValueError("invalid track identifier")
        if len(set(values)) != len(values):
            raise ValueError("duplicate track")
        return values
    tracks(data["favorites"])
    playlists=data["playlists"]
    if not isinstance(playlists,list) or len(playlists)>100:
        raise ValueError("invalid playlists")
    ids=set()
    for p in playlists:
        if not isinstance(p,dict) or set(p)!={"id","name","tracks"}:
            raise ValueError("invalid playlist")
        if not isinstance(p["id"],str) or not ID.fullmatch(p["id"]) or p["id"] in ids:
            raise ValueError("invalid playlist identifier")
        ids.add(p["id"])
        if not isinstance(p["name"],str) or not 1<=len(p["name"])<=120 or any(ord(c)<32 for c in p["name"]):
            raise ValueError("invalid playlist name")
        tracks(p["tracks"])
    prefs=data["preferences"]
    if not isinstance(prefs,dict) or set(prefs)-{"theme","repeat","shuffle"}:
        raise ValueError("unsupported preferences")
    if "theme" in prefs and prefs["theme"] not in ("system","light","dark"):
        raise ValueError("invalid theme")
    if "repeat" in prefs and prefs["repeat"] not in ("off","one","all"):
        raise ValueError("invalid repeat")
    if "shuffle" in prefs and type(prefs["shuffle"]) is not bool:
        raise ValueError("invalid shuffle")
    payload=json.dumps(data,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)
    if len(payload)>MAX_BYTES:
        raise ValueError("library too large")
    return payload

class CloudStore(IdentityStore):
    def __init__(self,path,pepper,**kwargs):
        super().__init__(path,pepper,**kwargs)
        with closing(sqlite3.connect(path)) as db:
            with db:
                db.execute(DDL)

    def read_library(self,account,verified_device):
        # Expired members can still export their metadata. No membership bypass.
        with self.transaction() as db:
            self._require_device(db,self._account(account),self._device(verified_device))
            row=db.execute("SELECT revision,payload FROM cloud_library_v2 WHERE account=?",(account,)).fetchone()
            return (row[0],json.loads(row[1])) if row else (0,None)

    def write_library(self,account,verified_device,expected_revision,data):
        if type(expected_revision) is not int or not 0<=expected_revision<2**63-1:
            raise ValueError("invalid revision")
        payload=normalize(data)
        with self.transaction() as db:
            self._require_device(db,self._account(account),self._device(verified_device))
            member=self._membership(db,account)
            now=self._now()
            if member is None or member.status(now)!="active":
                raise MembershipDenied("active membership required")
            row=db.execute("SELECT revision FROM cloud_library_v2 WHERE account=?",(account,)).fetchone()
            revision=row[0] if row else 0
            if revision!=expected_revision:
                raise RevisionConflict("refresh library before saving")
            db.execute("INSERT INTO cloud_library_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,updated_at=excluded.updated_at",(account,revision+1,payload,now))
            return revision+1

    def backup_for_upgrade(self, account, verified_device, expected_revision, data):
        """Atomically save reviewed metadata and rotate the single-use device
        recovery credential. This does not authorize playback or alter membership.
        A failed write leaves the prior backup and recovery credential unchanged.
        """
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**63-1:
            raise ValueError("invalid revision")
        account, device = self._account(account), self._device(verified_device)
        payload = normalize(data)
        replacement = secrets.token_urlsafe(32)
        with self.transaction() as db:
            self._require_device(db, account, device)
            member = self._membership(db, account)
            now = self._now()
            if member is None or member.status(now) != "active":
                raise MembershipDenied("active membership required")
            row = db.execute("SELECT revision,payload FROM cloud_library_v2 WHERE account=?", (account,)).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise RevisionConflict("review library before saving")
            # Do not silently replace the cloud library with an older or partial
            # device snapshot. Existing playlist order and preferences are preserved.
            if row:
                old = json.loads(row[1])
                new = json.loads(payload)
                if not set(old["favorites"]).issubset(new["favorites"]):
                    raise RevisionConflict("review favorite conflicts")
                incoming = {p["id"]: p for p in new["playlists"]}
                for playlist in old["playlists"]:
                    target = incoming.get(playlist["id"])
                    if target is None or target["name"] != playlist["name"]:
                        raise RevisionConflict("review playlist conflicts")
                    remaining = iter(target["tracks"])
                    if not all(any(track == current for current in remaining) for track in playlist["tracks"]):
                        raise RevisionConflict("review playlist track conflicts")
                if any(new["preferences"].get(k) != v for k,v in old["preferences"].items()):
                    raise RevisionConflict("review preference conflicts")
            if not row or row[1] != payload:
                revision += 1
                db.execute("INSERT INTO cloud_library_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,updated_at=excluded.updated_at",
                           (account, revision, payload, now))
            db.execute("UPDATE accounts_v2 SET recovery=? WHERE id=? AND device=?",
                       (self._digest("recovery", replacement), account, device))
            return revision, replacement

    def clear_library(self,account,verified_device,expected_revision):
        # Keep a revisioned empty snapshot so stale offline writes cannot resurrect it.
        if type(expected_revision) is not int or not 0<=expected_revision<2**63-1:
            raise ValueError("invalid revision")
        with self.transaction() as db:
            self._require_device(db,self._account(account),self._device(verified_device))
            row=db.execute("SELECT revision FROM cloud_library_v2 WHERE account=?",(account,)).fetchone()
            revision=row[0] if row else 0
            if revision!=expected_revision:
                raise RevisionConflict("refresh library before clearing")
            payload=normalize({"favorites":[],"playlists":[],"preferences":{}})
            db.execute("INSERT INTO cloud_library_v2 VALUES (?,?,?,?) ON CONFLICT(account) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,updated_at=excluded.updated_at",(account,revision+1,payload,self._now()))
            return revision+1
