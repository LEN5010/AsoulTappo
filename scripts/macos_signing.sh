#!/bin/bash
# macOS code signing for CI builds.
#   macos_signing.sh import          put the certificate from MACOS_CERTIFICATE (base64 .p12) and
#                                    MACOS_CERTIFICATE_PASSWORD into a temporary keychain codesign can use
#   macos_signing.sh verify <app>    fail unless <app> is signed with that certificate
#
# The certificate is self-signed. It does not satisfy Gatekeeper; it gives every build the same
# signing requirement (bundle identifier and certificate), so the Input Monitoring permission a
# player granted stays valid across updates. Unsigned builds are identified by their code hash,
# which changes with every build.
set -euo pipefail

IDENTITY="AsoulTappo Signing"

case "${1:-}" in
  import)
    if [ -z "${MACOS_CERTIFICATE:-}" ] || [ -z "${MACOS_CERTIFICATE_PASSWORD:-}" ]; then
      echo "MACOS_CERTIFICATE or MACOS_CERTIFICATE_PASSWORD is not set" >&2
      exit 1
    fi
    keychain="$RUNNER_TEMP/signing.keychain-db"
    keychain_password="$(uuidgen)"
    p12="$RUNNER_TEMP/signing.p12"
    echo "$MACOS_CERTIFICATE" | base64 --decode > "$p12"
    security create-keychain -p "$keychain_password" "$keychain"
    security set-keychain-settings -lut 21600 "$keychain"
    security unlock-keychain -p "$keychain_password" "$keychain"
    security import "$p12" -k "$keychain" -P "$MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
    rm -f "$p12"
    security set-key-partition-list -S apple-tool:,apple: -s -k "$keychain_password" "$keychain" > /dev/null
    # shellcheck disable=SC2046
    security list-keychains -d user -s "$keychain" $(security list-keychains -d user | tr -d '"')
    security find-identity -p codesigning "$keychain" | grep -q "$IDENTITY" || {
      echo "the keychain has no \"$IDENTITY\" identity" >&2
      exit 1
    }
    ;;
  verify)
    app="${2:?path to the .app}"
    codesign --verify --strict --deep "$app"
    requirement="$(codesign -d -r- "$app" 2>&1 | grep '^designated')"
    echo "$requirement"
    case "$requirement" in
      *"certificate root"*|*"certificate leaf"*) ;;
      *) echo "$app is not signed with the certificate" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "usage: $0 import | verify <app>" >&2
    exit 2
    ;;
esac
