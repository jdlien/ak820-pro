#!/usr/bin/env bash
# Build the firmware's battery.c and power.c, verbatim, against the stubs here
# and run every scenario in sim.c. The sources are COPIED beside the stubs so
# their relative #includes ("graphics/display.h", ...) find the stubs, not the
# firmware's real headers, which drag in ChibiOS and QMK.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="${BATTERY_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"   # override to test a mutant
fw="$here/../../qmk_firmware-ak820pro"
hist="$here/../../history"
log="$hist/battery-2026-09-25/charge-dumps/log-20260928-1034.csv"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$kb/battery.c" "$kb/battery.h" "$kb/power.c" "$kb/power.h" "$build/"
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
fail=0
for s in boot_battery boot_battery_clamp boot_usb_full discharge charge_log transitions \
         no_pack protection critical brief_plug unplug_mid_charge countdown_ease stale ring_restart \
         burst restore_needs_evidence charger_fault chrg_gap boot_charging_rise full_then_replug \
         reseat_survives_replug threshold_at_clamp log_cadence \
         reboot_after_full reboot_saved_mismatch reboot_below_clamp persist_tracks \
         warn_once warn_brief_plug warn_after_charge warn_cfg_rearms; do
    "$build/sim" "$s" "$log" || fail=1
done

# Phase 1b, B2: every recorded charge from flat replayed against TODAY's
# charging logic -- the baseline the new charging model is compared with.
"$build/sim" baseline_0928  "$log" || fail=1
"$build/sim" baseline_1001  "$hist/battery-2026-10-01-charge/log-20261001-1947.csv" || fail=1
"$build/sim" baseline_1004a "$hist/battery-2026-10-04-charge/log-20261004-2144.csv" || fail=1

# The replay adapter checked against the firmware that wrote the 10-04 log:
# 759e265796's battery.c, straight from git. Skipped for a mutant run.
if [ -z "${BATTERY_SIM_SRC:-}" ]; then
    old="$build/759e265796"
    mkdir -p "$old"
    cp -R "$here/stubs/." "$old/"
    for f in battery.c battery.h power.c power.h; do
        git -C "$fw" show "759e265796:keyboards/a_jazz/ak820pro/$f" > "$old/$f"
    done
    cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$old" \
       -o "$old/sim" "$here/sim.c" "$old/battery.c" "$old/power.c" -lm
    "$old/sim" replay_selfcheck "$hist/battery-2026-10-04-charge/log-20261004-2144.csv" || fail=1
fi
exit $fail
