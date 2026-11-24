# VOID Music: branding and source compatibility

**App identity:** VOID Music. **App developer/maintainer:** VOID. **Community:** https://discord.gg/marscm.

This fork keeps original music playback source providers unchanged while updating the app-facing UI, launcher labels, developer profile, Discord Rich Presence, recap, Android TV welcome and normal settings copy.

## Important distinctions

- Original Mochy Music authors and contributors remain credited in the GNU GPL-3.0 license, About credits and source repository. This is legally required; no claim is made to own their original work.
- Legacy Kotlin package names, Room schemas, resource identifiers, URI schemes, file formats and pairing protocol names may retain upstream prefixes for backward compatibility. Do not bulk replace those identifiers.
- The upstream Discord-gated module store is a separate service we do not control. Its endpoint is deliberately disabled; **MARS Community is a community link, not a replacement for the upstream store's authentication backend.**
- Previously generated backup folders or file names can still use legacy paths. Migrating existing backups requires a separate backward-compatible change.
- An Android **debug** build can be slower than an optimized **fast** or release build. Performance claims require device tests.
- GitHub Action test APKs are signed with temporary debug keys; Android may require removing a prior test APK before installing a newly built one. Back up any data first.
- App version and streaming coverage are not equivalent to licensing or permission to redistribute sound recordings.

Run `python3 scripts/void_brand_audit.py` to check English-facing identity. The audit reports untranslated strings as notices, not proof that every locale is fully updated. Do not merge while Android compilation, smoke testing or UI checks are failing.
