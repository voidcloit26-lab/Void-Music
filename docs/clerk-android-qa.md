# Clerk Android QA integration

This candidate uses the official Clerk Android UI SDK 1.5.0, released November 20, 2026. The optional source set is enabled only by VOID_CLERK_QA_ENABLED=true; default builds retain the current activation path. The bridge is not called by startup or routed from any screen yet.

## Required tenant configuration
- Create a dedicated VOID Music **development** instance; enable Native API, verified email codes, optional Google login. Do not enable production or paid services yet.
- Register Android namespace com.mochyy.mochymusic and the actual QA application ID (online.voidbot.music.fast if using the existing Fast flavor); register the stable application ID separately before release.
- Provide the development publishable key through build configuration only. The bridge accepts pk_test_ keys only. No Clerk secret key, JWT signing private key, wallet credential or Guardian pepper belongs in the APK.
- Validate a JWT template named void-music-api against a real signed token. The current backend verifier requires aud=void-music-api, sub, sid, exp, nbf, iat, issuer and approved azp where applicable. Custom JWT templates may require explicit session claims; do not relax validation to accommodate missing claims. Confirm actual session revocation and key rotation behavior before production.
- SDK session state is not membership authority. Registered device proof, signed leases and Guardian authorization remain mandatory.
- QA must test email OTP, Google callback if enabled, cancelled login, account switching, signed-out state, token expiry/revocation, mismatched identity, existing member migration, recovery, cloud isolation and full app compilation. The current default APK and API are unchanged.

References:
https://clerk.com/docs/android/getting-started/quickstart
https://clerk.com/docs/android/reference/native-mobile/auth
https://github.com/clerk/clerk-android/releases/tag/v1.5.0
