# Guardian activation API staging contract

The public-facing surface contains only POST /v1/challenge, /v1/redeem and /v1/status.
All successful entitlements are signed by the server and device-bound. The API exposes no
owner routes or secrets. It must be behind HTTPS; do not expose a development WSGI server.
Use a dedicated isolated service account, owner-only state and P-256 signing-key.pem (0600),
persistent pepper and secure backups. Run a production WSGI server using exactly one worker
process with bounded threads/timeouts, loopback or a private socket, and a TLS reverse proxy
enforcing a 4096 byte body cap and per-source rate limits. The application additionally has
a global bounded request budget; it does not trust forwarded IP headers. Restarting the
worker invalidates pending challenges, not entitlements. No public service is provisioned.

The Android GuardianClient uses HTTPS without redirects, bounded responses, device proof
and the release-pinned public signing key. The activation screen and service gates are not
yet wired. Do not give out activation codes or ship this source as a protected release.
Explicit verified-device inactivity clears the local receipt; generic denials, invalid
responses and connectivity errors do not. Offline lifetime access remains valid until an
online revocation check succeeds. Device binding is key possession, not attestation.
The existing transfer store function is not a supported device-transfer API; its account
lookup needs redesign before an owner can transfer a device-bound entitlement.

Run: python -m unittest discover -s guardian -v
Android compilation and TLS deployment/device verification remain separate release gates.
