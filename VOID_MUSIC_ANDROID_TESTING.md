# VOID Music — Android installation and playback test

**Status:** Development/testing only. Do not merge this branch into `main` or distribute the APK as a production release before validating functionality, signing and licensing.

## Build from GitHub Actions

1. Open `https://github.com/voidcloit26-lab/Void-Music/actions` and select the newest workflow run for branch `feat/void-music-branding-20261124`.
2. Watch the build step and check that the run ends in **success**. A failed or unstarted run is **not** an APK.
3. The `CI & Debug Build` workflow uploads the artifact `app-universal-gms-debug`. Alternatively the `Build PR` workflow uploads `app-universal-debug-pr-1`.
4. Download the artifact ZIP while logged into GitHub. Extract the `.apk` from the ZIP.
5. Verify the ZIP/APK matches the workflow for `voidcloit26-lab/Void-Music`, this development branch and a successful build. Avoid installing anything from random APK mirrors.
6. On an Android test device, open the APK file and approve installation from that trusted source if prompted. Android may warn that this is a debug build.

## Test only if APK compilation and installation succeed

- Confirm Android launcher displays **VOID Music** and a VOID vector mark.
- Check that playback works through search for multiple Hindi, Punjabi, English and international tracks.
- Verify seek, pause, resume, next, shuffle, queue, background lockscreen controls, Bluetooth and offline mode.
- Check album pages, playlists, downloads (where allowed), lyrics, sound quality and notifications.
- Verify crash-free startup and return to app; capture Android version, app build variant, track URL/id and precise playback failure messages.
- Verify provider/API terms before broader distribution. No complete global catalog or uninterrupted streaming is guaranteed.

## Build commands (desktop/CI)

```bash
./gradlew --console=plain assembleUniversalGmsDebug --no-configuration-cache --warning-mode summary
```

This branch retains the original upstream music provider implementations. Some OAuth integrations and the signed official upstream module store are not expected to work without independent configuration. Never commit API tokens or release signing credentials.
