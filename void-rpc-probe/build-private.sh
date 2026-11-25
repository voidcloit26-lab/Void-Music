#!/usr/bin/env bash
# Private, isolated developer build. Never uploads the SDK or APK.
set -euo pipefail
umask 077
if [[ $# -ne 2 ]]; then
  echo "Usage: bash void-rpc-probe/build-private.sh /absolute/path/discord_partner_sdk.aar /absolute/path/NEW-output-directory" >&2
  exit 2
fi
sdk="$(realpath "$1")"
out="$(realpath -m "$2")"
[[ -f "$sdk" && ! -e "$out" ]] || { echo "SDK missing or output directory already exists." >&2; exit 2; }
echo "ea4c080cc7c5ddeccab58f3bdf5682a3e18a7a84a815bb0f33609bfcafba3f99  $sdk" | sha256sum -c -
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
sha="$(git -C "$root" rev-parse HEAD)"
[[ -z "$(git -C "$root" status --porcelain --untracked-files=no -- void-rpc-probe)" ]] || { echo "Commit or discard probe changes first." >&2; exit 2; }
android="$(printenv ANDROID_SDK_ROOT || printenv ANDROID_HOME || true)"
[[ -n "$android" && -d "$android" ]] || { echo "Set ANDROID_HOME to the installed Android SDK." >&2; exit 2; }
export ANDROID_HOME="$android" ANDROID_SDK_ROOT="$android"
command -v gradle >/dev/null || { echo "Gradle 8.11.1 is required." >&2; exit 2; }
version="$(gradle --version)"
grep -q '^Gradle 8\.11\.1$' <<< "$version" || { echo "Expected Gradle 8.11.1." >&2; exit 2; }
for file in platforms/android-35/android.jar ndk/27.2.12479018/source.properties cmake/3.22.1/bin/cmake build-tools/35.0.0/apksigner build-tools/35.0.0/aapt; do
  [[ -e "$android/$file" ]] || { echo "Missing Android SDK component: $file" >&2; exit 2; }
done
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
git -C "$root" archive "$sha" void-rpc-probe | tar -xf - -C "$tmp"
cd "$tmp/void-rpc-probe"
mkdir -p app/libs
install -m 600 "$sdk" app/libs/discord_partner_sdk.aar
gradle --no-daemon --console=plain :app:assembleDebug
apk=app/build/outputs/apk/debug/app-debug.apk
test -s "$apk"
"$android/build-tools/35.0.0/apksigner" verify --verbose "$apk"
"$android/build-tools/35.0.0/aapt" dump permissions "$apk" > permissions.txt
if grep -E 'RECORD_AUDIO|BLUETOOTH_CONNECT|FOREGROUND_SERVICE_MICROPHONE' permissions.txt; then
  echo "Unexpected audio permissions; refusing to package." >&2; exit 1
fi
unzip -Z1 "$apk" > apk-files.txt
grep -Fxq 'lib/arm64-v8a/libvoid_rpc_probe.so' apk-files.txt
grep -Fxq 'lib/arm64-v8a/libdiscord_partner_sdk.so' apk-files.txt
mkdir -m 700 "$out"
install -m 600 "$apk" "$out/VOID-Presence-private-test.apk"
install -m 600 permissions.txt "$out/permissions.txt"
printf '%s\n' "$sha" > "$out/source-commit.txt"
(cd "$out" && sha256sum VOID-Presence-private-test.apk > SHA256SUMS && zip -q VOID-Presence-private-test.zip VOID-Presence-private-test.apk permissions.txt source-commit.txt SHA256SUMS)
echo "Private diagnostic ZIP: $out/VOID-Presence-private-test.zip"
echo "Not the combined music APK. Install only for authorized testing; verify live activity from a second account."
