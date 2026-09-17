#!/usr/bin/env bash
# sign-agent-macos.sh -- sign a local ak820-agent build with the Developer ID
# Application identity, the shape S3 established (plans/AK820-AGENT-CROSSPLATFORM-PLAN.md).
#
#   scripts/sign-agent-macos.sh [DIR] [--dylib PATH]
#
# DIR defaults to ak820-agent/target/release. Signs ak820-agent and ak820 in
# place, and the helper dylib found beside them (scripts/build-helper-macos.sh),
# or the one --dylib names (sign a copy you own, never the plugin's build output).
#
# Why it matters before Phase 6: TCC keys Automation consent on the designated
# requirement. An ad-hoc (linker) signature changes with every rebuild, so the
# daemon would ask for Automation again each time. And the identifier defaults
# to the file name, so it is set explicitly; a rename must not churn consent.
#
# By SHA-1, because the keychain lists the Application identity twice under one
# hash and a name is ambiguous. Hardened runtime, secure timestamp, and no
# entitlements: S3 found the empty set sufficient.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/ak820-agent/target/release"
DYLIB=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dylib) DYLIB="${2:?--dylib takes a path}"; shift 2 ;;
    -*) echo "usage: $0 [DIR] [--dylib PATH]" >&2; exit 2 ;;
    *) DIR="$1"; shift ;;
  esac
done

SHA1="$(security find-identity -v -p codesigning | awk '/Developer ID Application/ {print $2; exit}')"
[ -n "$SHA1" ] || { echo "no Developer ID Application identity in the keychain" >&2; exit 1; }

sign() {   # path identifier
  codesign --force --options runtime --timestamp --identifier "$2" --sign "$SHA1" "$1"
  codesign --verify --strict "$1"
  echo "  signed $1 as $2"
}

sign "$DIR/ak820-agent" com.jdlien.ak820pro.agent
sign "$DIR/ak820" com.jdlien.ak820pro.cli
# The vendored helper, when scripts/build-helper-macos.sh put it beside them.
[ -z "$DYLIB" ] && [ -f "$DIR/nowplaying-mediaremote.dylib" ] && DYLIB="$DIR/nowplaying-mediaremote.dylib"
[ -z "$DYLIB" ] || sign "$DYLIB" com.jdlien.ak820pro.mediaremote
