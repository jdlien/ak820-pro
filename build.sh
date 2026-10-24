#!/bin/zsh
# build.sh [daily|dev|devfault|instrumented|fpb] — build the AK820 Pro VIA firmware with provenance.
#
# daily        (default): console off, probes compiled out — what releases ship.
# dev:          daily plus the raw-HID bootloader jump (HC_BOOTLOADER), so
#               flash.sh needs no Fn+Esc, and the dev hooks (HC_DEVHOOK: press
#               Fn+D, read the display probe) for unattended display tests. What lives on JD's board while
#               development lasts; never released (release-firmware.sh takes
#               daily and fpb only, and the check below keeps the jump out of
#               both).
# devfault:     dev plus WDT_TEST_HOOKS, whose HC_BLITFAULT drops a real DMA
#               completion: the configuration menu's S0 proves its loss
#               recovery with it (plans/CONFIG-MENU-BUILD-PLAN.md). Gremlin's
#               board only; checked as a dev build.
# instrumented: console on + LOOPGAP_INSTRUMENT — for soak runs and debugging.
# fpb:          daily, but for the OTHER LCD panel revision — the one that comes
#               up upside down and colour-inverted on the default build. Shipped
#               in releases alongside the default so a stranger has both.
#
# Output: ak820pro-builds/out/via-<flavor>-<shorthash>[-dirty]-<timestamp>.bin
# Flash the per-build file it prints, never $QMK_HOME/a_jazz_ak820pro_via.bin —
# that path is shared and whoever compiles last owns it (see CLAUDE.md).
set -euo pipefail

if (( $# > 1 )); then echo "usage: build.sh [daily|dev|devfault|instrumented|fpb]" >&2; exit 2; fi
FLAVOR="${1:-daily}"
case "$FLAVOR" in
  daily)        FLAGS=();                        EXTRA="" ;;
  dev)          FLAGS=();                        EXTRA="-DAK820_RAW_BOOTLOADER -DAK820_DEV_HOOKS" ;;
  devfault)     FLAGS=();                        EXTRA="-DAK820_RAW_BOOTLOADER -DAK820_DEV_HOOKS -DWDT_TEST_HOOKS -DAK820_DEVFAULT" ;;
  instrumented) FLAGS=(-e CONSOLE_ENABLE=yes);   EXTRA="-DLOOPGAP_INSTRUMENT -DWDT_TEST_HOOKS" ;;
  fpb)          FLAGS=();                        EXTRA="-DAK820PRO_LCD_VARIANT_FPB" ;;
  *) echo "usage: build.sh [daily|dev|devfault|instrumented|fpb]" >&2; exit 2 ;;
esac
# The structural checks below treat devfault as the dev build it extends.
CHECK_AS="$FLAVOR"
[[ "$FLAVOR" == devfault ]] && CHECK_AS=dev
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
EXTRA_CC="$EXTRA -g -DAK820_BUILD_TOKEN=${token_hex}u"   # into FLAGS below, with the source's identity

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
# The configuration menu's About shows the source: eight hex digits as a
# number (no string through make's quoting), and whether it was dirty.
hash8=$(git -C "$REPO" rev-parse --short=8 HEAD | cut -c1-8)
FLAGS+=(-e "EXTRAFLAGS=$EXTRA_CC -DAK820_BUILD_HASH=0x${hash8}u -DAK820_BUILD_DIRTY=$([[ -n $dirty ]] && echo 1 || echo 0)")

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
# The bootloader jump by flavor: any process that can open raw HID can use it,
# so a released build (daily, fpb) must not carry it, and a dev build must.
jump=$(awk '$3 == "ak820_raw_bootloader"' <<<"$nm_out")
hooks=$(awk '$3 == "ak820_dev_hooks"' <<<"$nm_out")
case "$CHECK_AS" in
  daily|fpb) [[ -z "$jump" ]] || { echo "FAIL: a $FLAVOR build carries the raw-HID bootloader jump" >&2; fail=1; }
             [[ -z "$hooks" ]] || { echo "FAIL: a $FLAVOR build carries the dev hooks" >&2; fail=1; } ;;
  dev)       [[ -n "$jump" ]] || { echo "FAIL: the dev build lacks the raw-HID bootloader jump" >&2; fail=1; }
             [[ -n "$hooks" ]] || { echo "FAIL: the dev build lacks the dev hooks" >&2; fail=1; } ;;
esac
# The deep sleep (plans/DEEP-SLEEP-BUILD-PLAN.md, validation 8). Its
# production path is in every flavour: the ladder's question, the PCF's
# "before" read, the battery's hand-over and the driver's sleep pair, each
# reachable only through sleep_task, so with --gc-sections their presence
# says the path was linked. The bench's handlers that change what the board
# does (op 14's arm, light sleep, the bench sleep time, a held stage or mode,
# the acquisition's delay) are dev only: a released build answers none.
for sym in sleep_task power_sleep_wanted rtc_sleep_prepare battery_sleep_enter battery_sleep_account \
           sn32f2xx_sleep_enterI sn32f2xx_sleep_exitI rtc_wake_beginI sleep_page1_fill; do
  [[ -n "$(awk -v s=$sym '$3 == s' <<<"$nm_out")" ]] || { echo "FAIL: the deep sleep's $sym is missing" >&2; fail=1; }
done
if [[ "$FLAVOR" == (daily|fpb) ]]; then
  # power_set_mode left this list at the menu's P1a: its Power item calls it.
  for sym in sleep_deep_arm sleep_deep_cancel sleep_light_set power_set_bench_sleep_ms power_force_stage \
             rtc_dev_delay_full_once; do
    [[ -z "$(awk -v s=$sym '$3 == s' <<<"$nm_out")" ]] || { echo "FAIL: a $FLAVOR build carries $sym" >&2; fail=1; }
  done
fi
# The PCF's I2C may release the system lock at each byte (halconf.h's
# SW_I2C_BYTE_PREEMPT, the fallback driver's i2c_byte_boundary): dev builds
# only, behind their run-time switch, since measured it is no fix (the
# receiver is shallow; history/overrun-ab-20261019/). So both byte routines
# hold an unlock and a relock in a dev build and neither does in a released
# one. And the overrun measurement (overrun_diag.c, rtc.c's burst, sleep.c's
# wake ring) is dev only (plans/OVERRUN-CAPS-PLAN.md).
s_dis=$(arm-none-eabi-objdump -d --no-show-raw-insn "$s_elf")
for fn in i2c_write_byte i2c_read_byte; do
  body=$(awk -v f="<$fn>:" 'index($0, f) {p=1; next} p && /^$/ {exit} p' <<<"$s_dis")
  [[ -n "$body" ]] || { echo "FAIL: $fn not found (inlined? the preemption check needs it)" >&2; fail=1; continue; }
  if grep -q "cpsie" <<<"$body" && grep -q "cpsid" <<<"$body"; then rel=1; else rel=0; fi
  if grep -q "cpsie\|cpsid" <<<"$body"; then any=1; else any=0; fi
  case "$CHECK_AS" in
    dev)       (( rel )) || { echo "FAIL: the dev build's $fn lacks the switchable byte release" >&2; fail=1; } ;;
    daily|fpb) (( ! any )) || { echo "FAIL: a $FLAVOR build's $fn touches the lock between bytes" >&2; fail=1; } ;;
  esac
done
# The PCF's transfer runs unlocked with only the row ISR held off, in every
# flavour (plans/UART-LATENCY-PLAN.md, fix 1): its hooks must be linked.
for sym in ak820_i2c_xfer_begin ak820_i2c_xfer_end; do
  [[ -n "$(awk -v s="$sym" '$3 == s' <<<"$nm_out")" ]] || { echo "FAIL: $sym is missing (the unlocked PCF transfer)" >&2; fail=1; }
done
od_syms=(od_mask_begin od_uart_oe od_fill_summary rtc_burst_start sleep_wake_ring_fill od_tick od_set_uart_priority)
for sym in "${od_syms[@]}"; do
  have=$(awk -v s="$sym" '$3 == s' <<<"$nm_out")
  case "$CHECK_AS" in
    dev)       [[ -n "$have" ]] || { echo "FAIL: the dev build lacks $sym" >&2; fail=1; } ;;
    daily|fpb) [[ -z "$have" ]] || { echo "FAIL: a $FLAVOR build carries $sym" >&2; fail=1; } ;;
  esac
done
# The RAM floor (plans/CONFIG-MENU-BUILD-PLAN.md, C5): what's left between the
# static RAM and the stacks. The linker gives the whole remainder to a NOLOAD
# .heap (rules_memory.ld), so size's totals can't be subtracted from 32 KB;
# the gap is the heap's own bounds. Every flavour, before anything is
# published. The menu and every later stage together get at most 400 B of new
# static RAM; this floor is what keeps that honest.
heap_base=$(awk '$3 == "__heap_base__" {print $1}' <<<"$nm_out")
heap_end=$(awk '$3 == "__heap_end__" {print $1}' <<<"$nm_out")
if [[ -z "$heap_base" || -z "$heap_end" ]]; then
  echo "FAIL: __heap_base__ or __heap_end__ is missing from the ELF" >&2; fail=1
else
  heap_gap=$(( 0x$heap_end - 0x$heap_base ))
  echo "RAM: heap gap $heap_gap B (floor 128)"
  (( heap_gap >= 128 )) || { echo "FAIL: the heap gap is $heap_gap B, under the 128 B floor (C5)" >&2; fail=1; }
fi
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
