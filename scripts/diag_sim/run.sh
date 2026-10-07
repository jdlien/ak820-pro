#!/usr/bin/env bash
# Build the firmware's loop_acct.c and flash_stats.c (Phase 1b, D1 and C1),
# verbatim, against the stubs here; run sim.c's scenarios; then decode the
# pages they filled with hostagent/ak820health.py's own decoders.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="${DIAG_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$kb/loop_acct.c" "$kb/loop_acct.h" "$kb/flash_stats.c" "$kb/flash_stats.h" "$build/"
extra=()
if [ -f "$kb/rtc/rtc_persist.c" ]; then   # flash 2's C2 scheduler
    cp "$kb/rtc/rtc_persist.c" "$kb/rtc/rtc_persist.h" "$build/"
    extra=("$build/rtc_persist.c")
fi
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/loop_acct.c" "$build/flash_stats.c" ${extra[@]+"${extra[@]}"}
fail=0
for s in acct flash; do
    "$build/sim" "$s" > "$build/$s.out" || fail=1
    grep -v '^PAGE ' "$build/$s.out"
    python3 "$here/test_decode.py" < "$build/$s.out" || fail=1
done
if [ ${#extra[@]} -gt 0 ]; then
    "$build/sim" persist || fail=1
fi
exit $fail
