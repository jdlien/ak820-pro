#!/bin/zsh
# build.sh [daily|instrumented|fpb] — build the AK820 Pro VIA firmware with provenance.
#
# daily        (default): console off, probes compiled out — what lives on the board.
# instrumented: console on + LOOPGAP_INSTRUMENT — for soak runs and debugging.
# fpb:          daily, but for the OTHER LCD panel revision — the one that comes
#               up upside down and colour-inverted on the default build. Shipped
#               in releases alongside the default so a stranger has both.
#
# Output: ak820pro-builds/out/via-<flavor>-<shorthash>[-dirty]-<timestamp>.bin
# Flash the per-build file it prints, never $QMK_HOME/a_jazz_ak820pro_via.bin —
# that path is shared and whoever compiles last owns it (see CLAUDE.md).
set -euo pipefail

if (( $# > 1 )); then echo "usage: build.sh [daily|instrumented|fpb]" >&2; exit 2; fi
FLAVOR="${1:-daily}"
case "$FLAVOR" in
  daily)        FLAGS=();                        EXTRA="" ;;
  instrumented) FLAGS=(-e CONSOLE_ENABLE=yes);   EXTRA="-DLOOPGAP_INSTRUMENT -DWDT_TEST_HOOKS" ;;
  fpb)          FLAGS=();                        EXTRA="-DAK820PRO_LCD_VARIANT_FPB" ;;
  *) echo "usage: build.sh [daily|instrumented|fpb]" >&2; exit 2 ;;
esac
command -v xxd >/dev/null || { echo "ERROR: xxd not found" >&2; exit 1; }

# The build token (health page 6) names THIS build, so a fault PC the board
# reports finds its ELF through the manifest written below. Neither the
# artifact name nor QMK_BUILDDATE can: the name is stamped after compiling,
# and a dirty hash does not identify source content (crash-hunt review,
# finding 12). Random, nonzero; 0 means "an unarchived build".
token=0
while (( token == 0 )); do token=$(( 0x$(od -An -N4 -tx4 /dev/urandom | tr -d ' \n') )); done
token_hex=$(printf '0x%08x' "$token")
# -g: line info for the archived ELF. Debug info only; GCC's code generation
# does not depend on it (crash-hunt implementation review, finding 8).
FLAGS+=(-e "EXTRAFLAGS=$EXTRA -g -DAK820_BUILD_TOKEN=${token_hex}u")

WORK="$(cd "$(dirname "$0")" && pwd)"
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
python3 "$WORK/scripts/check_via_sync.py"   # enum <-> via.json index match
qmk compile -kb a_jazz/ak820pro -km via "${FLAGS[@]}"

[[ "$(state)" == "$pre_state" ]] || { echo "ERROR: repo changed during the build; artifact provenance unreliable — rebuild." >&2; exit 1; }

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
dest="$OUT/via-$FLAVOR-$hash$dirty-$stamp.bin"
elf="${dest%.bin}.elf"
manifest="${dest%.bin}.json"
# Staged under .partial names and published only after every check passes:
# a failure at ANY step -- a check, nm, a copy, the manifest -- leaves nothing
# that looks flashable (crash-hunt implementation review, finding 12).
s_bin="$dest.partial"; s_elf="$elf.partial"; s_json="$manifest.partial"
trap 'rm -f "$s_bin" "$s_elf" "$s_json"; rmdir "$LOCK" 2>/dev/null' EXIT
cp "$REPO/a_jazz_ak820pro_via.bin" "$s_bin"
# The ELF is what turns a fault PC into a function and line, and .build/ keeps
# only the LAST build's. Archived beside the .bin, under the lock.
cp "$REPO/.build/a_jazz_ak820pro_via.elf" "$s_elf"

# Structural checks (CLAUDE.md "Verifying a build") -- ENFORCED, not advisory:
# initial SP, reset vector, and the 0C45:8009 bcd 0100 USB device descriptor.
sp=$(xxd -l4 -e "$s_bin" | awk '{print $2}')
rv=$(xxd -s4 -l4 -e "$s_bin" | awk '{print $2}')
usb=$(xxd -p -c0 "$s_bin" | grep -c "450c09800001" || true)
fail=0
[[ "$sp" == "20000400" ]] || { echo "FAIL: initial SP 0x$sp != 0x20000400" >&2; fail=1; }
[[ "$rv" == "00000191" ]] || { echo "FAIL: reset vector 0x$rv != 0x00000191" >&2; fail=1; }
[[ "$usb" -ge 1 ]] || { echo "FAIL: USB descriptor 0C45:8009 bcd 0100 not found" >&2; fail=1; }
# The terminal handlers must have REPLACED ChibiOS's weak defaults: a silent
# fall-back to vectors.S would make every fault look like a hang again.
nm_out=$(arm-none-eabi-nm "$s_elf")
hf=$(awk '$3 == "HardFault_Handler" {print $1, $2}' <<<"$nm_out")
ue=$(awk '$3 == "_unhandled_exception" {print $2}' <<<"$nm_out")
[[ "${hf#* }" == "T" ]] || { echo "FAIL: HardFault_Handler is not ours (nm: '$hf')" >&2; fail=1; }
[[ "$ue" == "T" ]] || { echo "FAIL: _unhandled_exception is not ours (nm: '$ue')" >&2; fail=1; }
hf_vec=$(xxd -s12 -l4 -e "$s_bin" | awk '{print $2}')
hf_want=$(printf '%08x' $(( 0x${hf%% *} | 1 )))
[[ "$hf_vec" == "$hf_want" ]] || { echo "FAIL: HardFault vector 0x$hf_vec != handler 0x$hf_want" >&2; fail=1; }
# And the archive must be able to answer the question it exists for: the
# handler's own address resolves to its source file and a real line (-g).
hf_line=$(arm-none-eabi-addr2line -e "$s_elf" "0x${hf%% *}")
[[ "$hf_line" == *fault.c:[0-9]* ]] || { echo "FAIL: no line info in the ELF (addr2line: '$hf_line')" >&2; fail=1; }
if (( fail )); then echo "Structural checks FAILED; nothing published." >&2; exit 1; fi

# The manifest scripts/symbolize.sh resolves a board-reported token through.
python3 - "$s_bin" "$s_elf" "$s_json" "$dest" "$elf" "$token_hex" "$FLAVOR" "$EXTRA" \
    "$(git -C "$REPO" rev-parse HEAD)" "$dirty" \
    "$(sed -n 's/^#define QMK_BUILDDATE "\(.*\)"/\1/p' "$REPO"/.build/obj_a_jazz_ak820pro_via/src/version.h)" <<'PY'
import hashlib, json, os, sys
s_bin, s_elf, s_json, dest, elf, token, flavor, extra, head, dirty, builddate = sys.argv[1:]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
json.dump({"token": token, "flavor": flavor, "extraflags": extra, "git_head": head,
           "dirty": bool(dirty), "qmk_builddate": builddate,
           "bin": os.path.basename(dest), "bin_sha256": sha(s_bin),
           "elf": os.path.basename(elf), "elf_sha256": sha(s_elf)},
          open(s_json, "w"), indent=1)
PY

# Publish: the .bin LAST, since it is what gets flashed and it must never
# exist without the ELF and manifest that explain it.
mv "$s_elf" "$elf"; mv "$s_json" "$manifest"; mv "$s_bin" "$dest"

echo "BUILD OK: $dest  (token $token_hex)"
echo "flash:    $WORK/flash.sh \"$dest\"   # dumps+restores the VIA keymap around the flash"
