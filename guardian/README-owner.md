# VOID Guardian owner console (development)

The invitation store and local owner console are not connected to any production APK.
No live user redemption endpoint, Android activation gate, device attestation, or public owner login exists yet. Do not give these development codes to end users as working activation codes.

The console binds exclusively to 127.0.0.1. Use an interactive terminal under an isolated OS account and a dedicated local state directory (0700). Set VOID_GUARDIAN_STATE to its absolute path and VOID_GUARDIAN_PEPPER to a persistent, randomly generated 32-byte-or-longer hex secret from your secure local environment. Never place the pepper in Git, an APK, or chat. Back up the secret privately; changing it invalidates unredeemed codes.

Run from the repository root: python -m guardian.owner_web

The terminal prints an ephemeral Basic authentication password. Access http://127.0.0.1:8765 on the same machine (or forward that port using authenticated SSH). Never expose the port to the Internet. The password changes on restart. Generate a single or collective invitation, select redemption expiry, and copy the code immediately. Only the HMAC digest is stored. Fully redeemed/cancelled/expired invitations disappear; activation records remain. The console cleans expired keys during its loop.

For headless administration the existing python -m guardian.owner_cli generate --uses 1 --ttl 86400 command uses the same state.

Run tests: python -m unittest discover -s guardian -v

Future production gates: TLS, verified account identity, cryptographic device challenge, rate limiting, signed activation entitlement, Android Keystore, offline/revocation semantics, production database and audit, server-side owner authentication, and real device tests. No production changes made.
