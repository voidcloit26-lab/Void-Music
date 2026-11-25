# Staged Android activation gate

This is a development integration, not the final security boundary. The opt-in flag
VOID_GUARDIAN_ENFORCED requires VOID_GUARDIAN_ORIGIN and VOID_GUARDIAN_PUBLIC_KEY at
build time; only HTTPS host origins are accepted. Ordinary fast test builds remain
unrestricted while there is no staging server. Do not distribute any unprotected build
as the final private app. The public signing key is not a secret; never embed the
signing private key or invitation pepper.

The separate non-exported activation screen runs before phone/TV player UI and service
binding. It clears the entered invitation and supports signed status recovery. MusicService
rejects initialization, binding, controller sessions and starts when locked. The voice
entry point checks the same guard. This does not claim to cover all routes: app initialization,
download service, Android Auto UI, widgets, artwork provider, remote link, exported
callbacks, background revocation checks and already-connected controllers require separate
audit/enforcement. Test Android foreground service denial and locked activity lifecycle on
real devices before release. The app still needs a deployed TLS endpoint and stable release
signing. Offline receipts remain usable until a successful online revocation check.

No SDK AAR is included; no production deployment; no final APK.
