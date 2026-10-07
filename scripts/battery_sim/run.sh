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
[ -f "$kb/battery_tail.h" ] && cp "$kb/battery_tail.h" "$build/"   # flash 2's generated tail table
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
fail=0
for s in boot_battery boot_battery_clamp boot_usb_full discharge charge_log transitions \
         no_pack protection critical brief_plug unplug_mid_charge countdown_ease stale ring_restart \
         burst restore_needs_evidence charger_fault chrg_gap boot_charging_rise full_then_replug \
         reseat_survives_replug threshold_at_clamp log_cadence \
         reboot_after_full reboot_saved_mismatch reboot_below_clamp persist_tracks \
         warn_once warn_brief_plug warn_after_charge warn_cfg_rearms c5_equivalence; do
    "$build/sim" "$s" "$log" || fail=1
done

# Flash 2 (log v5): the charging model's scenarios (model.c), and the three
# charges from flat replayed against the model. sim.c compiles them only
# against a v5 battery.h.
if grep -qE '^#define BATTERY_LOG_VERSION +([5-9]|[1-9][0-9])\b' "$build/battery.h"; then
    model_scenarios="m_flat_boundary m_flat_boundary_above m_unknown_start m_partial_below_knee m_early_clamp \
             m_topup_near_full m_just_full m_delayed_termination m_delayed_unplug m_log_v5 m_log_saturated \
             m_ceil_hold30 m_ceil_60_29 m_ceil_60_30 m_ceil_clamp_hold m_ceil_clamp_entry m_ceil_clamp_exit \
             m_reports_lost_9 m_reports_lost_10 m_pause_short m_pause_before m_pause_after m_pause_relaxing \
             m_pause_missing m_pause_from_lost m_pause_from_unknown m_pause_then_unplug m_slow_charge \
             m_reseat_up m_reseat_down m_reseat_clamp m_reseat_unknown m_reseat_lost m_reseat_missing \
             m_reseat_replugs m_reseat_0929 m_full_fault m_full_holds"
    for s in $model_scenarios; do
        "$build/sim" "$s" || fail=1
    done
    "$build/sim" m_replay_0928  "$log" || fail=1
    "$build/sim" m_replay_1001  "$hist/battery-2026-10-01-charge/log-20261001-1947.csv" || fail=1
    "$build/sim" m_replay_1004a "$hist/battery-2026-10-04-charge/log-20261004-2144.csv" || fail=1

    # The model's scenarios again under AddressSanitizer and UBSan (B2): an
    # index past the tail table, or any overflow, aborts the run.
    cc -std=c11 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -Wall -Wextra \
       -Wno-unused-parameter -I"$build" -o "$build/sim_san" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
    san=0
    for s in $model_scenarios; do "$build/sim_san" "$s" > /dev/null 2>&1 || { echo "FAIL $s under the sanitizers"; san=1; }; done
    "$build/sim_san" m_replay_1001 "$hist/battery-2026-10-01-charge/log-20261001-1947.csv" > /dev/null 2>&1 \
        || { echo "FAIL m_replay_1001 under the sanitizers"; san=1; }
    [ $san = 0 ] && echo "ok   the model's scenarios under ASan and UBSan" || fail=1
fi

# A build of the board's battery.c and power.c AT A PINNED REVISION, straight
# from git, so what it checks cannot move when the working tree does.
pinned() {   # pinned <rev> <dir>
    mkdir -p "$2"
    cp -R "$here/stubs/." "$2/"
    for f in battery.c battery.h power.c power.h; do
        git -C "$fw" show "$1:keyboards/a_jazz/ak820pro/$f" > "$2/$f"
    done
    cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$2" \
       -o "$2/sim" "$here/sim.c" "$2/battery.c" "$2/power.c" -lm
}

if [ -z "${BATTERY_SIM_SRC:-}" ]; then
    # Phase 1b, B2: every recorded charge from flat replayed against TODAY's
    # charging logic -- flash 1's battery.c, dd5c94fdd9 -- the baseline flash
    # 2's model is compared with. Pinned (codex, gate 2): its output must equal
    # baseline-dd5c94fdd9.txt line for line, or the baseline has moved.
    base="$build/dd5c94fdd9"
    pinned dd5c94fdd9 "$base"
    { "$base/sim" baseline_0928  "$log"
      "$base/sim" baseline_1001  "$hist/battery-2026-10-01-charge/log-20261001-1947.csv"
      "$base/sim" baseline_1004a "$hist/battery-2026-10-04-charge/log-20261004-2144.csv"
    } > "$build/baseline.out" 2>&1 || fail=1
    grep -E '^(ok|FAIL)' "$build/baseline.out"
    if ! diff -u "$here/baseline-dd5c94fdd9.txt" "$build/baseline.out"; then
        echo "FAIL the pinned baseline's output changed (diff above)"; fail=1
    fi

    # The replay adapter checked against the firmware that wrote the 10-04
    # log: 759e265796's battery.c.
    old="$build/759e265796"
    pinned 759e265796 "$old"
    "$old/sim" replay_selfcheck "$hist/battery-2026-10-04-charge/log-20261004-2144.csv" || fail=1
fi
exit $fail
