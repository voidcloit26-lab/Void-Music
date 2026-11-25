#!/usr/bin/env bash
# Owner-controlled, offline Android signing key. Never runs in CI.
set -euo pipefail
umask 077
[[ $# == 1 && "$1" == /* ]] || { echo 'Usage: bash scripts/void-release-key.sh /absolute/private/new-directory' >&2; exit 2; }
command -v keytool >/dev/null
command -v openssl >/dev/null
out="$1"
[[ ! -e "$out" ]] || { echo 'Directory must not exist; refusing overwrite.' >&2; exit 2; }
mkdir -m 700 "$out"
echo 'Choose a unique strong signing password. Keep it in a password manager.'
keytool -genkeypair -keystore "$out/void-music-release.p12" -storetype PKCS12 -alias void-music-release -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 10000 -dname 'CN=VOID Music Release'
chmod 600 "$out/void-music-release.p12"
keytool -exportcert -alias void-music-release -keystore "$out/void-music-release.p12" -file "$out/void-music-public-cert.der"
openssl dgst -sha256 "$out/void-music-public-cert.der" > "$out/public-cert-sha256.txt"
echo 'Key generated locally. Back up the private PKCS12 securely and separately.'
echo 'Only the public certificate fingerprint may be shared. Never upload the key or password to chat or source control.'
