#!/usr/bin/env bash
# Build the firmware's battery.c and power.c, verbatim, against the stubs here
# and run every scenario in sim.c. The sources are COPIED beside the stubs so
# their relative #includes ("graphics/display.h", ...) find the stubs, not the
# firmware's real headers, which drag in ChibiOS and QMK.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="${BATTERY_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"   # override to test a mutant
log="$here/../../history/battery-2026-09-25/charge-dumps/log-20260928-1034.csv"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$kb/battery.c" "$kb/battery.h" "$kb/power.c" "$kb/power.h" "$build/"
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/battery.c" "$build/power.c"
fail=0
for s in boot_battery boot_battery_clamp boot_usb_full discharge charge_log transitions \
         no_pack protection critical brief_plug unplug_mid_charge countdown_ease stale ring_restart; do
    "$build/sim" "$s" "$log" || fail=1
done
exit $fail
