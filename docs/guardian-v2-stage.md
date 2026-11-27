# Guardian V2 staging (not deployed)

Use a new dedicated Neon database `void_guardian_v2_stage` and non-owner login
`guardian_v2_stage_runtime`, not the V1 database or credentials. The runtime
role must have no CREATE database/schema rights, including inherited/public
grants. Use TLS verify-full and SCRAM channel binding. Execute the guarded
one-time migration `guardian/deploy/v2-stage.sql` as the staging owner, after
verifying the database and taking a backup. Never run against the existing V1
database. No migration or deploy is executed automatically.

Proposed separate Render service, branch/commit pinned after QA:
- build: `pip install -r guardian/requirements-server.txt`
- start: `gunicorn --bind 0.0.0.0:$PORT --workers 2 'guardian.stage_app:create_app()'`
- health: `/healthz` (startup readiness only)
- require upstream per-client rate limits before public exposure.

Server-only environment keys:
- VOID_V2_STAGE_ENABLED=true
- VOID_V2_STAGE_DATABASE_URL (dedicated runtime URL, sslmode=verify-full)
- VOID_V2_STAGE_PEPPER (32–64 random bytes, hex)
- VOID_V2_CLERK_ISSUER (exact development issuer)
- VOID_V2_CLERK_RSA_PEM_B64 (trusted RSA public PEM, base64)
- VOID_V2_LEASE_PRIVATE_B64 (new P-256 private DER, base64)
- VOID_V2_LEASE_PUBLIC_KEY (matching public DER, base64url without padding)

No Clerk secret is needed by this pinned JWT verifier. Live session revocation,
key rotation, owner authorization, migration of V1 members and user/device QA
remain separate release requirements. No paid operations or audio distribution
are mounted. This stage uses only metadata and account-bound invitation codes.
Never paste private credentials into chats or commit them to Git.

Before deployment: run expanded isolated PostgreSQL tests, validate exact
migration and least-privilege grants in disposable staging, verify secret
configuration without logging values, and confirm no existing services change.
