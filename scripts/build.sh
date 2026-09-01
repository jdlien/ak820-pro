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

if (( $# > 1 )); then echo "usage: build.sh [daily|instrumented]" >&2; exit 2; fi
FLAVOR="${1:-daily}"
case "$FLAVOR" in
  daily)        FLAGS=() ;;
  instrumented) FLAGS=(-e CONSOLE_ENABLE=yes -e EXTRAFLAGS=-DLOOPGAP_INSTRUMENT) ;;
  *) echo "usage: build.sh [daily|instrumented]" >&2; exit 2 ;;
esac
command -v xxd >/dev/null || { echo "ERROR: xxd not found" >&2; exit 1; }

WORK="$(cd "$(dirname "$0")/.." && pwd)"
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

# Identity is captured BEFORE the build and re-checked after: a checkout that
# changes mid-build would otherwise stamp the artifact with the wrong source.
state() { echo "$(git -C "$REPO" rev-parse HEAD):$(git -C "$REPO" status --porcelain --untracked-files=no | shasum | cut -c1-8)"; }
pre_state=$(state)
hash=$(git -C "$REPO" rev-parse --short HEAD)
dirty=""
[[ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] && dirty="-dirty"

# qmk compile writes ONE shared output path; a lock serialises compile+copy so
# two invocations cannot interleave and mislabel each other's binary.
LOCK="$WORK/.build.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "ERROR: another build holds $LOCK (stale? rmdir it if no build is running)" >&2
  exit 1
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO"
qmk compile -kb a_jazz/ak820pro -km via "${FLAGS[@]}"

[[ "$(state)" == "$pre_state" ]] || { echo "ERROR: repo changed during the build; artifact provenance unreliable — rebuild." >&2; exit 1; }

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
dest="$OUT/via-$FLAVOR-$hash$dirty-$stamp.bin"
cp "$REPO/a_jazz_ak820pro_via.bin" "$dest"

# Structural checks (CLAUDE.md "Verifying a build") -- ENFORCED, not advisory:
# initial SP, reset vector, and the 0C45:8009 bcd 0100 USB device descriptor.
sp=$(xxd -l4 -e "$dest" | awk '{print $2}')
rv=$(xxd -s4 -l4 -e "$dest" | awk '{print $2}')
usb=$(xxd -p -c0 "$dest" | grep -c "450c09800001" || true)
fail=0
[[ "$sp" == "20000400" ]] || { echo "FAIL: initial SP 0x$sp != 0x20000400" >&2; fail=1; }
[[ "$rv" == "00000191" ]] || { echo "FAIL: reset vector 0x$rv != 0x00000191" >&2; fail=1; }
[[ "$usb" -ge 1 ]] || { echo "FAIL: USB descriptor 0C45:8009 bcd 0100 not found" >&2; fail=1; }
if (( fail )); then rm -f "$dest"; echo "Structural checks FAILED; artifact removed." >&2; exit 1; fi

echo "BUILD OK: $dest"
echo "flash:    $WORK/flash.sh \"$dest\"   # dumps+restores the VIA keymap around the flash"
