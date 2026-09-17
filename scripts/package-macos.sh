#!/usr/bin/env bash
# package-macos.sh -- the macOS release: build, sign, disk image, notarize, staple.
#
#   scripts/package-macos.sh                  test, build, sign, make the .dmg, verify.
#                                             Stops BEFORE anything is sent to Apple.
#   scripts/package-macos.sh --submit DMG     notarize the .dmg built above, staple, verify
#   scripts/package-macos.sh --allow-dirty    build from a dirty tree (never for a release)
#
# Apple silicon only, macOS 15 or later (decided 2026-09-16: one owner, recent
# Macs; the perl-hosted helper exists because of 15.4 anyway).
#
# Notarization uses a notarytool keychain profile, by default the one the Stream
# Deck plugin set up (../streamdeck-now-playing/build/notarize-setup.sh). It holds
# an app-specific password for the Apple ID, not for any one app, so it serves
# this release too. Nothing secret is in this repository.
#
# Three findings are baked in (plans/AK820-AGENT-CROSSPLATFORM-PLAN.md, S3 and
# the plugin's own packaging):
#   1. Every extended attribute is stripped before signing. A stray
#      com.apple.quarantine on the helper hangs perl behind a Gatekeeper dialog.
#   2. Each binary gets an explicit --identifier: the default is the file name,
#      and TCC keys Automation consent on it, so a rename would re-ask.
#   3. A bare Mach-O cannot hold a stapled ticket; a disk image can. So the .dmg
#      is what gets notarized and stapled, and it verifies offline afterwards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="$ROOT/ak820-agent"
TRIPLE=aarch64-apple-darwin
MIN_MACOS=15.0
PROFILE="${NOTARY_PROFILE:-NowPlayingNotary}"
OUT="$AGENT/target/dist"

identity() {
  security find-identity -v -p codesigning | awk '/Developer ID Application/ {print $2; exit}'
}

# ---------------------------------------------------------------- submit mode
if [ "${1:-}" = "--submit" ]; then
  DMG="${2:?--submit takes the .dmg path}"
  [ -f "$DMG" ] || { echo "no such file: $DMG" >&2; exit 1; }
  xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1 || {
    echo "notary profile '$PROFILE' is missing or not working;" >&2
    echo "  set one up: ../streamdeck-now-playing/build/notarize-setup.sh '<secrt-url>'" >&2
    exit 1
  }
  echo "==> submitting $DMG to Apple's notary service (waits for the verdict)"
  RESULT="$(xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait --output-format json)"
  STATUS="$(printf '%s' "$RESULT" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))')"
  ID="$(printf '%s' "$RESULT" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
  echo "    submission $ID: $STATUS"
  if [ "$STATUS" != "Accepted" ]; then
    echo "==> not accepted; Apple's log follows" >&2
    xcrun notarytool log "$ID" --keychain-profile "$PROFILE" >&2 || true
    exit 1
  fi
  echo "==> stapling"
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  echo "==> Gatekeeper, as a downloaded file would meet it"
  spctl -a -t open --context context:primary-signature -v "$DMG"
  shasum -a 256 "$DMG"
  echo "==> done: $DMG is notarized and stapled"
  exit 0
fi

# ----------------------------------------------------------------- build mode
ALLOW_DIRTY=0
[ "${1:-}" = "--allow-dirty" ] && ALLOW_DIRTY=1

cd "$ROOT"
if [ "$ALLOW_DIRTY" = 0 ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "refusing: the tree has uncommitted changes (a release must be a commit); --allow-dirty to override" >&2
  exit 1
fi
SHA1="$(identity)"
[ -n "$SHA1" ] || { echo "no Developer ID Application identity in the keychain" >&2; exit 1; }
"$ROOT/scripts/check-helper-upstream.sh" || {
  echo "refusing: the vendored helper is behind the plugin's; re-vendor it first" >&2
  exit 1
}

VERSION="$(git describe --tags --dirty)"
NAME="ak820-agent-macos-$VERSION"
STAGE="$OUT/$NAME"
DMG="$OUT/$NAME.dmg"
echo "==> $NAME (Apple silicon, macOS $MIN_MACOS+)"

echo "==> tests"
TESTLOG="$(mktemp)"
if ! (cd "$AGENT" && cargo test --locked >"$TESTLOG" 2>&1); then
  grep -E "FAILED|panicked" "$TESTLOG" >&2 || tail -20 "$TESTLOG" >&2
  echo "tests failed (full output: $TESTLOG)" >&2
  exit 1
fi
grep -E "^test result" "$TESTLOG" | awk '{p += $4} END {print "    " p " passed"}'
rm -f "$TESTLOG"

echo "==> building the daemon and CLI"
(cd "$AGENT" && MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS" cargo build --release --locked --target "$TRIPLE" --quiet)

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp "$AGENT/target/$TRIPLE/release/ak820" "$AGENT/target/$TRIPLE/release/ak820-agent" "$STAGE/"

echo "==> building the MediaRemote helper"
# The plugin's flags (helper/UPSTREAM), plus the release's architecture and floor.
clang -arch arm64 -mmacosx-version-min="$MIN_MACOS" \
  -dynamiclib -fobjc-arc -O2 -framework Foundation \
  -o "$STAGE/nowplaying-mediaremote.dylib" "$AGENT/helper/nowplaying-mediaremote.m"

cp "$AGENT/INSTALL-macos.txt" "$STAGE/INSTALL.txt"
cp "$AGENT/helper/LICENSE" "$STAGE/LICENSE-mediaremote-helper.txt"

echo "==> stripping extended attributes"
xattr -cr "$STAGE"

echo "==> signing with $SHA1"
sign() {  # path identifier
  codesign --force --options runtime --timestamp --identifier "$2" --sign "$SHA1" "$1"
  codesign --verify --strict "$1"
}
sign "$STAGE/nowplaying-mediaremote.dylib" com.jdlien.ak820pro.mediaremote
sign "$STAGE/ak820-agent" com.jdlien.ak820pro.agent
sign "$STAGE/ak820" com.jdlien.ak820pro.cli

echo "==> checking what was built"
for f in ak820 ak820-agent nowplaying-mediaremote.dylib; do
  arch="$(lipo -archs "$STAGE/$f")"
  minos="$(xcrun vtool -show-build "$STAGE/$f" | awk '/minos/ {print $2; exit}')"
  [ "$arch" = arm64 ] || { echo "$f is $arch, not arm64" >&2; exit 1; }
  [ "$minos" = "$MIN_MACOS" ] || { echo "$f has minos $minos, not $MIN_MACOS" >&2; exit 1; }
  echo "    $f: arm64, macOS $minos+, $(codesign -dv "$STAGE/$f" 2>&1 | awk -F= '/^Identifier/ {print $2}')"
done
REPORTED="$("$STAGE/ak820" --version)"
echo "    $REPORTED"
case "$REPORTED" in *dirty*) [ "$ALLOW_DIRTY" = 1 ] || { echo "the binary says dirty" >&2; exit 1; } ;; esac

echo "==> disk image"
hdiutil create -volname "AK820 Agent" -srcfolder "$STAGE" -ov -format UDZO "$DMG" -quiet
codesign --force --timestamp --sign "$SHA1" "$DMG"
codesign --verify --strict "$DMG"
echo "    Gatekeeper now (expected to say Unnotarized until --submit):"
spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 | sed 's/^/      /' || true
shasum -a 256 "$DMG"

echo "==> ready, nothing sent to Apple. To notarize and staple:"
echo "      scripts/package-macos.sh --submit \"$DMG\""
