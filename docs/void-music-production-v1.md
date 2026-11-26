# VOID Music V1 production plan — isolated candidate

Baseline: 5c045aaff941893ccd0254604d4b3f167f7c6469 (working internal APK).
No live deployment, migration, release publication or signing-key change is authorized by this branch alone.

## Sequence and release gates
1. Permanent account identity: random server ID, passkey (WebAuthn / Android Credential Manager), hashed one-time recovery codes, device key challenge. No IMEI, phone tracking or hidden file. Android ID only optional recognition, not authentication. Existing active installations claim an account using verified legacy key possession; revoked accounts cannot migrate. Lost legacy keys require owner-assisted recovery, never automatic entitlement transfer based on a numeric ID alone.
2. Cloud metadata: account-scoped playlists, favorites, saved albums/artists, preferences, optional history, revision/conflict handling and explicit export/delete. Do not upload audio or private local-file paths. Keep recovery credentials separate from backups. Test reinstall and offline reconnection.
3. Update center: signed stable policy, separate release signing key, immutable versioned APK, authenticated download, verified SHA-256 and expected APK signer/package/version, Android installer confirmation. Stable minimum defaults to latest; test channel isolated. Persist last verified policy, reject replay, restrict online access for obsolete supported clients. No unverified outage can invent a required update. Keep update/recovery UI reachable; preserve data. Offline lease needs explicit design, testing, and migration from lifetime receipts. Older legacy offline APKs cannot be retroactively forced to update.
4. Owner controls: account/device replacement, audit logs, recovery and revocation, publish/promote release, version stats with privacy controls. Emergency policy rollback uses a higher policy sequence; APK recovery uses a fixed build with a higher versionCode.
5. UI: keep working player intact; fix misleading native connection label and preview overlap, use glass preview only in app, Spotify search default when exact link unavailable, keep MARS button. Discord controls actual activity rendering.
6. Branding and legal: translate visible legacy strings, audit icons/links, keep accessible About legal notices and GPL corresponding source, review Discord SDK and music provider permissions before distribution.
7. Production signing: permanent key with secure offline backup, stable package online.voidbot.music, monotonic versionCode, R8 and resource shrinking, release verification, no test key. Existing .fast test app cannot directly update to a different package/signing identity; migrate accounts and library first. Never commit private signing or server keys.
8. Validate isolated PostgreSQL, Android compilation, migration, recovery, authorization, updater tampering and outage cases; full phone QA; only then promote approved release.

Initial implementation: guardian/release_policy.py and tests, not connected to live API or Android.
Keep VOID Bot, Lavalink and MARS services/databases unchanged.
