# Deployment verification

The loopback HTTP smoke test exercises the real WSGI request boundary, signature verification, one-use invitation consumption, restart persistence, challenge invalidation after restart and revocation. It deliberately does not represent internet-facing TLS, Gunicorn concurrency, proxy policy, or real Android tests.

The private main-app build helper is `scripts/build-void-native-private.sh`. It packages only an explicitly authorized ARM64 Fast integration test, verifies the SDK digest and APK signature, records the merged manifest and native libraries, and never uploads the SDK or APK. It requires a separate Android build machine; do not run it on the production bot VPS. It intentionally does not enforce live Guardian activation until the independent server is provisioned. No final release credentials are used.
