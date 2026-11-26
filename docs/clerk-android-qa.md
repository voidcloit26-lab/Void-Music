# Clerk Android QA integration

This candidate uses the official Clerk Android UI SDK 1.5.0, released November 20, 2026. The optional source set is enabled only by VOID_CLERK_QA_ENABLED=true; default builds retain the current activation path. The bridge is not called by startup or routed from any screen yet.

## Required tenant configuration
- Create a dedicated VOID Music **development** instance; enable Native API, verified email codes, optional Google login. Do not enable production or paid services yet.
- Register Clerk Android namespace android_app and the actual QA application ID (online.voidbot.music.fast if using the existing Fast flavor); register the stable application ID separately before release.
- The registered QA issuer is https://living-tadpole-5182.clerk.accounts.dev. Supply the development publishable key through VOID_CLERK_QA_PUBLISHABLE_KEY in the opted-in build configuration. The bridge accepts pk_test_ keys only. No Clerk secret key, JWT signing private key, wallet credential or Guardian pepper belongs in the APK.
- Customize the actual Clerk session token (Sessions > Customize session token) with the static claim {"aud":"void-music-api"}. Use getToken() without a template: standalone JWT templates do not contain sid. Validate the actual signed token and preserve mandatory issuer, audience, sub, sid, exp, nbf, iat and origin checks. If Clerk rejects the aud customization, stop and revise the verified token contract; never weaken checks silently. Confirm actual session revocation and key rotation behavior before production.
- SDK session state is not membership authority. Registered device proof, signed leases and Guardian authorization remain mandatory.
- QA must test email OTP, Google callback if enabled, cancelled login, account switching, signed-out state, token expiry/revocation, mismatched identity, existing member migration, recovery, cloud isolation and full app compilation. The current default APK and API are unchanged.

References:
https://clerk.com/docs/android/getting-started/quickstart
https://clerk.com/docs/android/reference/native-mobile/auth
https://github.com/clerk/clerk-android/releases/tag/v1.5.0
