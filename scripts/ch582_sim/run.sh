#!/usr/bin/env bash
# Build the firmware's CH582F driver, verbatim, against the stubs here and run
# every case in harness.c (Phase 1b, D1: the transport counters). Built with
# the daily flavor's flags: RAW_ENABLE, and neither CONSOLE_ENABLE nor
# WDT_TEST_HOOKS -- the counters must exist where the soaks run.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="${CH582_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth}"   # override to test a mutant
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$src/ch582f_ajazz.c" "$src/ch582f_ajazz.h" "$build/"
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -DRAW_ENABLE -I"$build" \
   -o "$build/harness" "$here/harness.c" "$build/ch582f_ajazz.c"
fail=0
for c in withheld queue_full replaced not_replaced_none_behind not_replaced_head uart_errors; do
    "$build/harness" "$c" || fail=1
done
exit $fail
