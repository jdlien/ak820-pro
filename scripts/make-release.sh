#!/usr/bin/env bash
# make-release.sh -- assemble the artifacts a non-builder needs, with checksums.
#
# Output: ak820pro-builds/release/
#   ak820pro-via.bin        default LCD panel
#   ak820pro-via-fpb.bin    the other panel revision (upside down / inverted on default)
#   flash_assets.bin        LCD assets: fonts, icons, splash
#   via.json                the VIA definition (the board is not in VIA's database)
#   SHA256SUMS
#
# Does NOT publish anything. Upload with:
#   gh release create vX.Y.Z ak820pro-builds/release/* --repo jdlien/ak820-pro
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/ak820pro-builds/release"
BOARD="$ROOT/qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"

rm -rf "$OUT"; mkdir -p "$OUT"

# Both panel variants, from the same source revision. A stranger cannot tell
# which revision they have until the panel lights up, so shipping one is
# shipping a coin flip.
for flavour in daily fpb; do
  line=$("$ROOT/build.sh" "$flavour" | grep '^BUILD OK:')
  src=${line#BUILD OK: }
  case "$flavour" in
    daily) cp "$src" "$OUT/ak820pro-via.bin" ;;
    fpb)   cp "$src" "$OUT/ak820pro-via-fpb.bin" ;;
  esac
  echo "  $flavour <- $(basename "$src")"
done

# Regenerate the asset image, then prove it belongs with these binaries: mkraw
# assigns ids by SORTED FILENAME, so an added or renamed source silently
# renumbers everything and the firmware's committed flash_assets.h no longer
# describes what is on the chip. Same source revision is NOT sufficient.
( cd "$ROOT/time-util-ak820pro/assets" && "$ROOT/venv/bin/python" mkraw.py --flash >/dev/null )
if ! diff -q "$ROOT/time-util-ak820pro/assets/flash_assets.h" \
              "$BOARD/graphics/res/flash_assets.h" >/dev/null; then
  echo "ERROR: generated flash_assets.h differs from the firmware's copy." >&2
  echo "       The assets and the binaries would not match. Rebuild the firmware" >&2
  echo "       after copying the new header in -- see docs/fonts-assets.md." >&2
  exit 1
fi
cp "$ROOT/time-util-ak820pro/assets/flash_assets.bin" "$OUT/"
cp "$BOARD/via.json" "$OUT/"

( cd "$OUT" && shasum -a 256 ./* > SHA256SUMS )
echo
echo "release payload in $OUT:"
( cd "$OUT" && ls -la && echo && cat SHA256SUMS )
