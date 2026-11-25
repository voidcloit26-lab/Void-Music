#!/usr/bin/env bash
# Isolated SDK-enabled integration test, not a release or a production-server task.
set -euo pipefail
umask 077
if [[ $# != 2 || "${VOID_NATIVE_RPC_AUTHORIZED_PRIVATE_TEST:-}" != true ]]; then
  echo "Authorized private testing only. Usage: bash scripts/build-void-native-private.sh /absolute/sdk.aar /absolute/new-output-dir" >&2
  exit 2
fi
[[ "$1" == /* && "$2" == /* ]] || { echo "Use absolute paths." >&2; exit 2; }
sdk="$(realpath "$1")"
out="$(realpath -m "$2")"
[[ -f "$sdk" && ! -e "$out" ]] || { echo "SDK missing or output already exists." >&2; exit 2; }
printf '%s  %s\n' 'ea4c080cc7c5ddeccab58f3bdf5682a3e18a7a84a815bb0f33609bfcafba3f99' "$sdk" | sha256sum -c -
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
sha="$(git -C "$root" rev-parse HEAD)"
[[ -z "$(git -C "$root" status --porcelain --untracked-files=no)" ]] || { echo "Commit tracked changes first." >&2; exit 2; }
android="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
[[ -d "$android" ]] || { echo "Set Android SDK path." >&2; exit 2; }
export ANDROID_HOME="$android" ANDROID_SDK_ROOT="$android"
if [[ ! -f "$android/platforms/android-37.0/android.jar" && ! -f "$android/platforms/android-37/android.jar" ]]; then
  echo "Missing Android SDK platform 37.0." >&2; exit 2
fi
for file in ndk/27.0.12077973/source.properties cmake/3.22.1/bin/cmake; do
  [[ -e "$android/$file" ]] || { echo "Missing SDK component: $file" >&2; exit 2; }
done
java -version 2>&1 | grep -Eq 'version "21([."]|$)' || { echo "JDK 21 required." >&2; exit 2; }
signer="$(find "$android/build-tools" -mindepth 2 -maxdepth 2 -name apksigner -type f | sort -V | tail -n1)"
[[ -x "$signer" && -x "$(dirname "$signer")/aapt" ]] || { echo "Missing Android build-tools." >&2; exit 2; }
for cmd in git tar unzip zip sha256sum python3; do command -v "$cmd" >/dev/null || exit 2; done
# Never load production service config, sign with a release key, or upload artifacts.
unset STORE_PASSWORD KEY_ALIAS KEY_PASSWORD
unset VOID_GUARDIAN_ENFORCED VOID_GUARDIAN_ORIGIN VOID_GUARDIAN_PUBLIC_KEY
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
git -C "$root" archive "$sha" | tar -xf - -C "$tmp"
cd "$tmp"
export VOID_NATIVE_RPC_AAR="$sdk"
export CMAKE_BUILD_PARALLEL_LEVEL=1
# Test variant uses the local Android debug key; no permanent release credentials.
bash gradlew --no-daemon --console=plain --no-configuration-cache --max-workers=1 :app:assembleArm64GmsFast
mapfile -t apks < <(find app/build/outputs/apk/arm64Gms/fast -maxdepth 1 -name '*.apk' -type f)
[[ ${#apks[@]} == 1 && -s "${apks[0]}" ]] || { echo "Expected exactly one fast ARM64 APK." >&2; exit 1; }
apk="${apks[0]}"
"$signer" verify --verbose --print-certs "$apk" > signature.txt
"$(dirname "$signer")/aapt" dump badging "$apk" > badging.txt
grep -q "^package: name='online.voidbot.music.fast'" badging.txt
"$(dirname "$signer")/aapt" dump permissions "$apk" > permissions.txt
"$(dirname "$signer")/aapt" dump xmltree "$apk" AndroidManifest.xml > manifest.txt
# The original player uses microphone/Bluetooth for its own features. Reject SDK microphone FGS
# and inspect SDK components; do not strip existing player permissions indiscriminately.
if grep -E 'FOREGROUND_SERVICE_MICROPHONE' permissions.txt; then
  echo "Unexpected microphone foreground-service permission. Review merged manifest." >&2
  exit 1
fi
unzip -Z1 "$apk" > apk-files.txt
grep -Fxq 'lib/arm64-v8a/libvoid_music_rpc.so' apk-files.txt
grep -Fxq 'lib/arm64-v8a/libdiscord_partner_sdk.so' apk-files.txt
mkdir -m 700 "$out"
install -m 600 "$apk" "$out/VOID-Music-private-integration.apk"
for file in signature.txt badging.txt permissions.txt manifest.txt; do install -m 600 "$file" "$out/$file"; done
printf '%s\n' "$sha" > "$out/source-commit.txt"
(cd "$out" && sha256sum VOID-Music-private-integration.apk > SHA256SUMS && zip -q VOID-Music-private-integration.zip VOID-Music-private-integration.apk signature.txt badging.txt permissions.txt manifest.txt source-commit.txt SHA256SUMS)
echo "Private integration test only: $out"
echo "Review merged manifest and test real playback/clear/second-account visibility. No distribution."
