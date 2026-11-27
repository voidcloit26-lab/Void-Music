# Staging account entry (not a production release)

When VOID_CLERK_QA_ENABLED=true and the configured development public key is
present, a non-exported activity is enabled and Settings displays "VOID account · staging QA".
It points only at the dedicated Render staging hostname, sets FLAG_SECURE to
protect recovery codes from casual screenshots, and never grants V1 playback.
The menu is absent in V1-enforced builds. Ordinary builds compile a disabled
stub with no Clerk SDK dependency. No new APK has been published.

The server is intentionally locked until database credentials, Clerk JWT
verification and signing keys are provisioned. Compile both QA-on and QA-off
variants before generating an APK. Check that the QA screen cannot be launched
by another app and that the regular player is unaffected.
