# VOID RPC Probe — isolated local test source

This is a separate diagnostic application, not the VOID Music player or a production release. It contains no proprietary SDK files. Before using the Discord SDK for a non-game application, confirm eligibility with Discord and review the terms. Do not distribute a combined GPL/proprietary APK without resolving the licensing issue. This probe is not a conclusion that the licenses are compatible.

## Build locally after confirming eligibility

Use JDK 17, Gradle 8.11.1, Android SDK API 35, NDK 27.2.12479018, and CMake 3.22.1. Copy the unmodified release `discord_partner_sdk.aar` from your authorized Discord developer download to `app/libs/discord_partner_sdk.aar`. Do not publish the AAR or headers to the source repository. Run `gradle :app:assembleDebug` from this directory. The test APK should be at `app/build/outputs/apk/debug/app-debug.apk` if compilation succeeds. This project has no wrapper; use a trusted local Gradle installation. No bot token, OAuth token or secret is needed.

## Test

On an ARM64 Android phone with Discord installed and signed in, enable activity sharing in Discord, install the separate test package, open it and press Publish test activity. Keep the probe visible and have a friend check the profile; the test clears when the probe stops. The uploaded asset key is `void_music`, application ID is `1553388915300245594`. The two buttons link to YouTube Music and MARS Community. Clear the activity explicitly when finished. The optional Connect and share current song action reads metadata from the selected VOID Music app using Android MediaBrowser. It never uses notification access or sends playback commands. Public artwork is opt-in and restricted to selected public HTTPS image hosts. Title, artist and timestamps are shared only while the test screen is open; pause, stop or leave the probe to clear the activity. Verify the merged manifest and audio routing on device before any wider testing.

## Validation and limits

C++ JNI translation unit syntax-checked using the supplied public SDK headers and host JDK JNI headers. Android build, link, manifest merge, client behavior and visible Discord presence are unverified. This now includes a foreground-only real-song synchronization diagnostic, in addition to the fixed test activity. Background publishing is not implemented or verified. If approved and successful, design a genuinely independent companion using opt-in Android media sessions, or obtain compatible linking rights for an in-app integration. Avoid private gateway or user-token automation. Keep existing bot and music player unchanged.

The GitHub workflow on branch test runs source-only validation and Guardian unit tests. It does not bundle the proprietary SDK or produce an APK.

Official docs:
- https://discord.com/developers/docs/social-sdk/release_notes.html
- https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence
- https://support-dev.discord.com/hc/en-us/articles/30225844245271-Discord-Social-SDK-Terms
