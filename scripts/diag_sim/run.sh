#!/usr/bin/env bash
# Build the firmware's loop_acct.c and flash_stats.c (Phase 1b, D1 and C1),
# verbatim, against the stubs here; run sim.c's scenarios; then decode the
# pages they filled with hostagent/ak820health.py's own decoders. Then the
# settings block (kb_eeconfig.c, verbatim: kbee.c, the menu's P2a).
#
# DIAG_SIM_GOLDEN_BASE=<qmk commit> also builds that commit's flash_stats.c
# (a 7-byte block: before P2a) and requires pages 0-2 byte-identical to this
# one's under the old fields' workload (P2's proof: "the old pages
# byte-identical"). CC and PYTHON pick the tools (default cc, python3).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="${DIAG_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"
cc="${CC:-cc}"
py="${PYTHON:-python3}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$kb/loop_acct.c" "$kb/loop_acct.h" "$kb/flash_stats.c" "$kb/flash_stats.h" "$build/"
extra=()
if [ -f "$kb/rtc/rtc_persist.c" ]; then   # flash 2's C2 scheduler
    cp "$kb/rtc/rtc_persist.c" "$kb/rtc/rtc_persist.h" "$build/"
    extra=("$build/rtc_persist.c")
fi
"$cc" -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/loop_acct.c" "$build/flash_stats.c" ${extra[@]+"${extra[@]}"}
fail=0
for s in acct flash; do
    "$build/sim" "$s" > "$build/$s.out" || fail=1
    grep -v '^PAGE ' "$build/$s.out"
    "$py" "$here/test_decode.py" < "$build/$s.out" || fail=1
done
if [ ${#extra[@]} -gt 0 ]; then
    "$build/sim" persist || fail=1
fi

# The settings block, in its own build: the real kb_eeconfig.h replaces the
# RTC-only stub, and stubs_kbee/ adds what kb_eeconfig.c includes.
kbee="$build/kbee.d"
mkdir -p "$kbee"
cp -R "$here/stubs/." "$kbee/"
cp -R "$here/stubs_kbee/." "$kbee/"
cp "$kb/kb_eeconfig.c" "$kb/kb_eeconfig.h" "$kb/indicators.h" "$kb/indicator_levels.h" "$kbee/"
"$cc" -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$kbee" -o "$kbee/kbee" "$here/kbee.c" "$kbee/kb_eeconfig.c"
"$kbee/kbee" || fail=1

if [ -n "${DIAG_SIM_GOLDEN_BASE:-}" ]; then
    old="$build/old.d"
    mkdir -p "$old"
    cp -R "$here/stubs/." "$old/"
    cp "$kb/loop_acct.c" "$kb/loop_acct.h" "$old/"
    git -C "$kb" show "$DIAG_SIM_GOLDEN_BASE:./flash_stats.c" > "$old/flash_stats.c"
    git -C "$kb" show "$DIAG_SIM_GOLDEN_BASE:./flash_stats.h" > "$old/flash_stats.h"
    "$cc" -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -DEECONFIG_KB_DATA_SIZE=7 -I"$old" \
       -o "$old/sim" "$here/sim.c" "$old/loop_acct.c" "$old/flash_stats.c"
    "$old/sim" golden > "$old/golden.out"
    "$build/sim" golden > "$build/golden.out"
    if cmp -s "$old/golden.out" "$build/golden.out"; then
        echo "ok   golden: pages 0-2 byte-identical to $DIAG_SIM_GOLDEN_BASE's flash_stats.c"
    else
        echo "FAIL golden: pages 0-2 differ from $DIAG_SIM_GOLDEN_BASE's"
        diff "$old/golden.out" "$build/golden.out" || true
        fail=1
    fi
fi
exit $fail
