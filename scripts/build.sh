#!/bin/zsh
# build.sh [daily|instrumented] — build the AK820 Pro VIA firmware with provenance.
#
# daily        (default): console off, probes compiled out — what lives on the board.
# instrumented: console on + LOOPGAP_INSTRUMENT — for soak runs and debugging.
#
# Output: ak820pro-builds/out/via-<flavor>-<shorthash>[-dirty]-<timestamp>.bin
# Flash the per-build file it prints, never $QMK_HOME/a_jazz_ak820pro_via.bin —
# that path is shared and whoever compiles last owns it (see CLAUDE.md).
set -euo pipefail

WORK="$(cd "$(dirname "$0")/.." && pwd)"
FLAVOR="${1:-daily}"
source "$WORK/env.sh"
REPO="$QMK_HOME"
OUT="$WORK/ak820pro-builds/out"

# The chibios-contrib patches are commits on the pinned branch now. Refuse to
# build a tree whose submodule is not exactly at the gitlink, or is dirty --
# that is how the silently-wrong-binary class of failure starts.
gitlink=$(git -C "$REPO" ls-tree HEAD lib/chibios-contrib | awk '{print $3}')
subhead=$(git -C "$REPO/lib/chibios-contrib" rev-parse HEAD)
if [[ "$gitlink" != "$subhead" ]]; then
  echo "ERROR: lib/chibios-contrib HEAD ($subhead) != superproject gitlink ($gitlink)." >&2
  echo "       Fix with: git -C \"$REPO/lib/chibios-contrib\" checkout ak820pro-patches (see PATCHES.md)" >&2
  exit 1
fi
if [[ -n "$(git -C "$REPO/lib/chibios-contrib" status --porcelain)" ]]; then
  echo "ERROR: lib/chibios-contrib working tree is dirty; commit or revert before building." >&2
  exit 1
fi

case "$FLAVOR" in
  daily)        FLAGS=() ;;
  instrumented) FLAGS=(-e CONSOLE_ENABLE=yes -e EXTRAFLAGS=-DLOOPGAP_INSTRUMENT) ;;
  *) echo "usage: build.sh [daily|instrumented]" >&2; exit 2 ;;
esac

cd "$REPO"
qmk compile -kb a_jazz/ak820pro -km via "${FLAGS[@]}"

hash=$(git -C "$REPO" rev-parse --short HEAD)
dirty=""
[[ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] && dirty="-dirty"
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
dest="$OUT/via-$FLAVOR-$hash$dirty-$stamp.bin"
cp "$REPO/a_jazz_ak820pro_via.bin" "$dest"

# Structural sanity (CLAUDE.md "Verifying a build"): initial SP and reset vector.
sp=$(xxd -l4 -e "$dest" | awk '{print $2}')
rv=$(xxd -s4 -l4 -e "$dest" | awk '{print $2}')
if [[ "$sp" != "20000400" || "$rv" != "00000191" ]]; then
  echo "WARNING: vector table unexpected (SP=0x$sp reset=0x$rv; want 0x20000400/0x00000191)" >&2
fi

echo "BUILD OK: $dest"
echo "flash:    $WORK/flash.sh \"$dest\"   # dumps+restores the VIA keymap around the flash"
