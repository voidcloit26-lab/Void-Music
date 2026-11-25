# Free-tier deployment using an independent Neon database

This is a staging option, not an existing deployment. Create a dedicated Neon
project and database for Guardian. Do not reuse MARS, VOID Bot, or their roles.
Use a dedicated database role, direct connection URL, and verified TLS.
Set the connection string's sslmode to verify-full and ensure the host has the
trusted CA certificates needed by libpq.

Render environment variables, entered directly in the service settings:
- VOID_GUARDIAN_DATABASE_URL (secret, dedicated Neon connection)
- VOID_GUARDIAN_PEPPER (secret, stable random hex of at least 32 bytes)
- VOID_GUARDIAN_SIGNING_KEY_B64 (secret, stable P-256 PKCS8 DER, standard base64)
- VOID_GUARDIAN_BIND=0.0.0.0:10000 (if PORT is 10000; match the platform's port)

Do not use a random generated signing key per startup. Back up the key and pepper
securely. Only its DER public key in unpadded URL-safe base64 goes in the Android
build. Do not send secret values via chat or commit them. A dedicated Neon role
must be able to create the void_guardian schema initially; the adapter uses
only that schema and a transaction advisory lock.

Build command: pip install -r guardian/requirements-server.txt
Start command: gunicorn --config guardian/deploy/gunicorn.conf.py 'guardian.activation_api:create_app()'

No SQLite activation data is copied by this change; begin with the new dedicated
database, not an existing live installation. Existing SQLite users, if any,
would need a separately audited migration. Free-tier cold starts may delay
activation; mobile timeouts/retry behavior must be tested. Keep the owner console
private: free Render web services do not necessarily provide SSH or a persistent
management shell; a separately authenticated owner-management solution is still
required before release. The public activation API exposes no owner routes.
