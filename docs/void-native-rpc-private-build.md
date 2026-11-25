# Main app native activity — private test source
The Android player now sends its existing NowPlaying and PresenceSettings to a native local
RPC bridge when built with the authorized SDK. No Discord token, bot or gateway is involved.
Default builds omit the SDK and display preview only. Fresh native opt-in and a separate
public-artwork consent are required. Animated/local art falls back to a public still or logo.
Updates are serialized on the main dispatcher and deduplicated, rate-limited and retried.
Pause (default), stop, offline mode, revoked Guardian access and disable request a clear.
An SDK acceptance callback is not proof that another user can see the activity.

Do not set VOID_NATIVE_RPC_AUTHORIZED_PRIVATE_TEST=true unless your intended private
test is authorized by the SDK terms. Supply the local verified AAR path in
VOID_NATIVE_RPC_AAR; never commit it or upload the combined APK to GitHub artifacts.
The combined private build needs the main app toolchain (Gradle wrapper 9.3.1, JDK21,
Android SDK 37, NDK 27.0.12077973). The existing diagnostic uses a different toolchain.
This source has not passed a combined SDK build, native runtime test or distribution
licensing review. Obtain appropriate authorization and GPL compatibility before sharing.
Only the ordinary SDK-free CI build may publish its development artifact.
No final APK is issued from this checkpoint.
