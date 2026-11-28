"""Private, single-use release downloads for the isolated Guardian staging service.

The ticket is issued only after a device-signed request. A download requires
the same verified Clerk session and still-linked device. APKs are streamed
from a pre-provisioned read-only directory, not from client-controlled URLs.
"""
import hashlib
import hmac
import os
import re
import secrets
import stat
from pathlib import Path
from guardian.clerk_session import SessionDenied
from guardian.membership_rules import MembershipDenied
from guardian.release_policy import verify_policy


class DownloadUnavailable(RuntimeError):
    pass


class DownloadTickets:
    def __init__(self, store, *, capacity=1024):
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise ValueError("invalid download ticket capacity")
        self.store, self.capacity = store, capacity
        with store.transaction() as db:
            db.execute("SELECT digest,identity,session_digest,account,device,sequence,expires_at FROM release_downloads_v2 LIMIT 0")

    def _session(self, session):
        return hmac.digest(self.store.pepper, ("release-session-v2:" + session.issuer + ":" + session.session_id).encode("ascii"), hashlib.sha256)

    def _check_account(self, db, identity, account, device):
        if not db.execute("SELECT 1 FROM external_identity_v2 WHERE identity=? AND account=?", (identity, account)).fetchone():
            raise MembershipDenied("download denied")
        self.store._require_device(db, account, device)
        member = self.store._membership(db, account)
        if member is None or member.status(self.store._now()) not in ("active", "expired"):
            raise MembershipDenied("download denied")

    def issue(self, session, account, device, sequence):
        if type(sequence) is not int or not 1 <= sequence <= 2**63-1:
            raise ValueError("invalid release sequence")
        identity = self.store._identity(session.issuer, session.subject)
        account, device = self.store._account(account), self.store._device(device)
        session_digest = self._session(session)
        token = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            self._check_account(db, identity, account, device)
            now = self.store._now()
            db.execute("DELETE FROM release_downloads_v2 WHERE expires_at<=?", (now,))
            # Replace previous unused ticket for this identity. No unbounded rows.
            db.execute("DELETE FROM release_downloads_v2 WHERE identity=?", (identity,))
            if db.execute("SELECT count(*) FROM release_downloads_v2").fetchone()[0] >= self.capacity:
                raise DownloadUnavailable("download capacity")
            db.execute("INSERT INTO release_downloads_v2 VALUES (?,?,?,?,?,?,?)",
                       (self.store._digest("release-download",token),identity,session_digest,account,device,sequence,now+120))
        return token

    def consume(self, session, token, sequence):
        digest = self.store._digest("release-download",token)
        identity = self.store._identity(session.issuer,session.subject)
        session_digest = self._session(session)
        with self.store.transaction() as db:
            row = db.execute("SELECT identity,session_digest,account,device,sequence,expires_at FROM release_downloads_v2 WHERE digest=?", (digest,)).fetchone()
            if (not row or not hmac.compare_digest(row[0],identity) or not hmac.compare_digest(row[1],session_digest)
                    or row[4] != sequence or row[5] <= self.store._now()):
                raise MembershipDenied("download denied")
            self._check_account(db,identity,row[2],row[3])
            db.execute("DELETE FROM release_downloads_v2 WHERE digest=?", (digest,))


class ReleaseFiles:
    def __init__(self, directory):
        self.root = Path(directory).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("release directory required")

    def open_verified(self, policy):
        # Never use a request parameter to build the path. Only verified digest.
        if not re.fullmatch(r"[a-f0-9]{64}",policy.apk_sha256):
            raise DownloadUnavailable("invalid artifact digest")
        fd = os.open(self.root / (policy.apk_sha256 + ".apk"), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        file = os.fdopen(fd, "rb")
        try:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != policy.apk_bytes:
                raise DownloadUnavailable("artifact size mismatch")
            digest = hashlib.sha256()
            remaining = policy.apk_bytes
            while remaining:
                block = file.read(min(1024*1024,remaining))
                if not block:
                    raise DownloadUnavailable("truncated artifact")
                digest.update(block)
                remaining -= len(block)
            if file.read(1) or not hmac.compare_digest(digest.hexdigest(),policy.apk_sha256):
                raise DownloadUnavailable("artifact digest mismatch")
            file.seek(0)
            return file
        except BaseException:
            file.close()
            raise


class ReleaseDownloadAPI:
    def __init__(self, verifier, registry, tickets, files, fairness, reply, *, budget):
        self.verifier,self.registry,self.tickets,self.files,self.fairness,self.reply = verifier,registry,tickets,files,fairness,reply
        self.budget = budget

    def __call__(self, env, start):
        match = re.fullmatch(r"/v2/releases/([1-9][0-9]{0,18})/apk",env.get("PATH_INFO",""))
        if not match or env.get("QUERY_STRING") or env.get("HTTP_ORIGIN") or env.get("HTTP_COOKIE"):
            return self.reply(start,"404 Not Found",{"error":"not_found"})
        if env.get("REQUEST_METHOD") != "GET":
            return self.reply(start,"405 Method Not Allowed",{"error":"method_not_allowed"})
        auth=env.get("HTTP_AUTHORIZATION","")
        ticket=env.get("HTTP_X_VOID_RELEASE_TICKET","")
        if not isinstance(auth,str) or not auth.startswith("Bearer ") or not 7 < len(auth) <= 8199:
            return self.reply(start,"401 Unauthorized",{"error":"invalid_session"})
        if not isinstance(ticket,str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}",ticket):
            return self.reply(start,"403 Forbidden",{"error":"access_denied"})
        file = None
        try:
            session = self.verifier.verify(auth[7:])
            sequence = int(match[1])
            release = self.registry.current()
            if release is None:
                raise DownloadUnavailable("release unavailable")
            policy = verify_policy(*release,self.registry.public_key,int(self.registry.clock()))
            if policy.sequence != sequence:
                return self.reply(start,"409 Conflict",{"error":"release_changed"})
            # Consume before expensive disk hashing: even a valid replay cannot
            # repeatedly hash or stream the file. A failed download needs a new ticket.
            self.tickets.consume(session,ticket,sequence)
            # Invalid tickets cannot consume download bandwidth quotas. A valid
            # ticket is single-use even when throttled; obtain a fresh one later.
            if not self.fairness.take((session.issuer,session.subject)) or not self.budget.take():
                return self.reply(start,"429 Too Many Requests",{"error":"retry_later"})
            file = self.files.open_verified(policy)
            body = _DownloadBody(file)
            start("200 OK",[("Content-Type","application/vnd.android.package-archive"),
                 ("Content-Length",str(policy.apk_bytes)),("Cache-Control","private, no-store"),
                 ("X-Content-Type-Options","nosniff"),("Content-Disposition","attachment; filename=VOID-Music.apk")])
            return body
        except SessionDenied:
            status,value="401 Unauthorized",{"error":"invalid_session"}
        except MembershipDenied:
            status,value="403 Forbidden",{"error":"access_denied"}
        except Exception:
            status,value="503 Service Unavailable",{"error":"release_unavailable"}
        if file is not None:
            file.close()
        return self.reply(start,status,value)


class _DownloadBody:
    def __init__(self,file):
        self.file=file
    def __iter__(self):
        return self
    def __next__(self):
        chunk=self.file.read(64*1024)
        if not chunk:
            self.close()
            raise StopIteration
        return chunk
    def close(self):
        self.file.close()
