# Consolidated release gates (VOID Music)

The existing protected fast APK is test-only. The R8 preflight compiles an unsigned, SDK-free release configuration and publishes verification reports only, never an APK. A successful preflight is not proof of installability, runtime performance or production readiness.

Before distributing one final ZIP:
- Obtain independent evidence the activation server's signing public key equals the immutable build pin, and rotate any staging signing key with uncertain provenance using securely generated keys before production. Do not transmit private keys or pepper in chat.
- Verify owner login, invitation generation, redemption, restoration, cancellation and online revocation on an actual Android device; confirm UI, animation, playback, offline and background behavior.
- Confirm SDK authorization and GPL-compatible redistribution before including native Discord SDK; the current SDK-enabled helper is private test-only. Validate real Rich Presence visibility from a separate account.
- Provision an owner-controlled permanent signing keystore outside source control, back it up securely and verify its public certificate digest independently. Never use the fast/debug signer.
- Build the optimized protected release, verify exact package/signature/Guardian config, runtime behavior and licensing, and prepare corresponding GPL source for the recipients. Review tracked source and artifacts for secrets before packaging.
- Package only the verified APK and concise installation/checksum instructions for the user, plus appropriate source and license materials separately. Do not publish keys, mapping files, credentials or proprietary SDK files without authorization.

Keep all work on test until approved. No changes to VOID Bot, other services, or the existing music player.
