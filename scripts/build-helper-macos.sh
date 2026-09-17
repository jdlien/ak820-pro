#!/usr/bin/env bash
# build-helper-macos.sh -- build the vendored MediaRemote helper beside the
# daemon, where `ak820 install` and the daemon look for it.
#
#   scripts/build-helper-macos.sh [OUT_DIR]     (default ak820-agent/target/release)
#
# The flags are the plugin's own (ak820-agent/helper/UPSTREAM). Then sign it with
# scripts/sign-agent-macos.sh, which signs a helper it finds in the same dir.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/ak820-agent/target/release}"
mkdir -p "$OUT"
clang -dynamiclib -fobjc-arc -O2 -framework Foundation \
  -o "$OUT/nowplaying-mediaremote.dylib" "$ROOT/ak820-agent/helper/nowplaying-mediaremote.m"
echo "  built $OUT/nowplaying-mediaremote.dylib"
