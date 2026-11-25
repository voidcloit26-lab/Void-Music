# VOID native presence integration checkpoint

## Device result — 25 November 2026
The owner supplied a screenshot of their own Discord profile showing "Listening to VOID Music",
"Rich Presence test", "VOID Music - test activity" and a running timer (0:15).
The isolated ARM64 probe built from 18eb774 was signed and installed successfully.
This is evidence of fixed activity publication, not a test of song synchronization,
external viewers, buttons, artwork, pause/seek, or clearing after process death.

## Next source layer
NativePresenceMapper converts the existing PresenceActivity into a transport-neutral payload:
same configured title/detail/state/type, millisecond timestamps, provider link, fixed MARS
community link and conservative public artwork selection. It does not change the player,
preview, settings screen, playback service or legacy authentication. No networking is added.
The native SDK is not included or linked in this music build.

Artwork is opt-in; no local or private image upload. Animated art uses a permitted public still
or the registered logo. Existing animated preview settings remain intact, but live animation
and playback badges require additional support. The native payload retains the application name
request; actual displayed name and button visibility are subject to Discord behavior.

## Remaining gates
- Confirm applicable Social SDK authorization and GPL compatibility before embedding or
  distributing the proprietary SDK with the GPL-derived music app. If not permitted, keep a
  separately installed authorized companion using a documented media-session boundary.
- Implement the supported transport with a single serialized SDK lifecycle, callbacks,
  bounded retry, explicit enable/disable, clear on pause/stop/offline, no account tokens.
- Wire real MusicService updates and existing settings only after transport tests.
- Test live track transitions, seeking, background, stop, art, both buttons and other-account view.
- Complete Guardian startup/service enforcement and signed release verification separately.
- Do not change main, production bot or Lavalink. No release APK is ready at this checkpoint.

Regression target: `:app:testUniversalGmsFastUnitTest` (NativePresenceMapperTest).
This test target has not yet been executed on a full Android toolchain at this checkpoint.
