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
[ -f "$kb/rgb_matrix_kb.inc" ] && cp "$kb/rgb_matrix_kb.inc" "$build/"   # the colour build's effects
qroot="$(cd "$kb/../../.." && pwd)"   # the tree $kb is in: QMK's quantum/color.c for the colour build
[ -f "$kb/battery_tail.h" ] && cp "$kb/battery_tail.h" "$build/"   # flash 2's generated tail table
# The menu's P2b (10-25): the backlight 0-100 on indicator_levels.h's table,
# once display.c has no 24-entry bkl_duty[] (sim.c's SIM_BKL_100). The pinned
# builds below have no sim_bkl.h: the 24 levels, as their firmware has.
if [ -f "$kb/indicator_levels.h" ] && ! grep -q 'static const uint8_t bkl_duty\[\]' "$kb/graphics/display.c"; then
    cp "$kb/indicator_levels.h" "$build/"
    echo '#define SIM_BKL_100 1' > "$build/sim_bkl.h"
fi
cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -I"$build" \
   -o "$build/sim" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
fail=0
# Phase 2's scenarios (ladder.c, count.c) and the two drains they replay.
phase2="l_normal l_modes l_usb l_low_cap l_val_cap l_lights_cut l_announce l_persisted l_minimal l_minimal_enter l_minimal_owed l_low_alert l_sleep l_sleep_low l_sleep_usb l_wake_notice l_wake_notice_high
        l_no_lights_off l_ceiling_moves l_low_edge l_unknown_level
        c_rate c_uneven c_wrap c_hold c_ratchet c_floor_cut c_time_left c_load_step c_usb_data
        c_stale c_excursion c_bias c_clamp_cross c_reboot
        c_band_top c_band_top_edge c_floor_boot c_cut_reseat c_hold_stale c_handover_stays c_floor_entry c_clamp_marker"
# Deep sleep (sleeps.c): only against a battery.c with the hand-over.
grep -q "BATTERY_P_SLEEP_UW" "$build/battery.h" && phase2="$phase2 s_energy s_time_left s_floor_cut s_unknown s_band_hold s_remainder s_relax s_log_within s_log_across s_log_long s_log_wrap_order s_log_pending s_log_recovery_boundary s_usb s_no_wake s_replay_v7 s_log_floor s_replay_mixed s_log_late_cut s_usb_relax_banked"
r3="$hist/battery-2026-10-15-drain-2f/log-20261018-0205-rgbcut.csv"
e2="$hist/battery-2026-10-12-drain-2e/log-20261014-0950-preswap.csv"
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
    model_scenarios="m_flat_boundary m_flat_boundary_above m_flat_burst m_flat_burst_above m_flat_unknown_first m_unknown_start m_partial_below_knee m_early_clamp m_early_clamp_below \
             m_topup_near_full m_just_full m_delayed_termination m_delayed_unplug m_log_v5 m_log_saturated \
             m_ceil_hold30 m_ceil_60_29 m_ceil_60_30 m_ceil_clamp_hold m_ceil_clamp_entry m_ceil_clamp_exit \
             m_reports_lost_9 m_reports_lost_10 m_pause_short m_pause_before m_pause_after m_pause_after_unadopted m_handover_unplug_replug m_pause_relaxing \
             m_pause_missing m_pause_from_lost m_pause_from_unknown m_pause_then_unplug m_slow_charge \
             m_reseat_up m_reseat_up_plateau m_reseat_down m_reseat_down_steep m_reseat_clamp m_reseat_unknown m_reseat_lost m_reseat_missing \
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
    if grep -q '^#define POWER_HAS_MODES' "$build/power.h"; then
        for s in $phase2; do "$build/sim_san" "$s" > /dev/null 2>&1 || { echo "FAIL $s under the sanitizers"; san=1; }; done
        "$build/sim_san" c_replay_r3 "$r3" > /dev/null 2>&1 || { echo "FAIL c_replay_r3 under the sanitizers"; san=1; }
    fi
    [ $san = 0 ] && echo "ok   the model's scenarios under ASan and UBSan" || fail=1
fi

# Phase 2: the power modes (ladder.c), against a power.h that has them.
if grep -q '^#define POWER_HAS_MODES' "$build/power.h"; then
    for s in $phase2; do
        "$build/sim" "$s" || fail=1
    done
    # The drains, replayed through the firmware and scored every second: R3 to
    # the cut, 2e to its reboot, each interval's reports interleaved, shuffled,
    # and as the monotone ramp (a stress case, allowed 4 points).
    for v in "" _shuf _ramp; do
        "$build/sim" c_replay_r3$v "$r3" || fail=1
        "$build/sim" c_replay_2e$v "$e2" || fail=1
    done

    # The dev build's power.c (AK820_DEV_HOOKS: the bench's held stage, mode
    # and sleep time, HC_DEVHOOK op 14): every scenario again, since the hooks
    # must change nothing until used, then the ones that use them.
    if grep -q 'want_val' "$build/power.c"; then
        cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -DAK820_DEV_HOOKS -I"$build" \
           -o "$build/sim_dev" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
        dev=0
        for s in $phase2; do "$build/sim_dev" "$s" > /dev/null || { echo "FAIL $s in the dev-hooks build"; dev=1; }; done
        [ $dev = 0 ] && echo "ok   every power scenario in the dev-hooks build" || fail=1
        devonly="l_forced_ceiling l_set_mode l_under_dim l_low_minimal_held c_lights_off_held"
        for s in $devonly; do
            "$build/sim_dev" "$s" || fail=1
        done
        # ... and under the sanitizers, as the plain build's are above.
        cc -std=c11 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -Wall -Wextra \
           -Wno-unused-parameter -DAK820_DEV_HOOKS -I"$build" -o "$build/sim_dev_san" "$here/sim.c" \
           "$build/battery.c" "$build/power.c" -lm
        san=0
        for s in $devonly; do "$build/sim_dev_san" "$s" > /dev/null 2>&1 || { echo "FAIL $s under the sanitizers"; san=1; }; done
        [ $san = 0 ] && echo "ok   the dev-hooks scenarios under ASan and UBSan" || fail=1
    fi
    # The devfault build (AK820_DEVFAULT, build.sh) keeps 8 log entries fewer
    # for the configuration menu's RAM (plans/CONFIG-MENU-P1-DESIGN.md): the
    # log's scenarios again against 712, wrap and oldest-first included. The
    # 720 runs above stay.
    if grep -q 'AK820_DEVFAULT' "$build/battery.c"; then
        cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -DAK820_DEV_HOOKS -DWDT_TEST_HOOKS -DAK820_DEVFAULT \
           -DSIM_LOG_LEN=712u -I"$build" -o "$build/sim_fault" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
        for s in s_log_within s_log_across s_log_long s_log_wrap_order s_log_pending s_log_recovery_boundary s_log_floor s_log_late_cut; do
            "$build/sim_fault" "$s" || fail=1
        done
        for s in log_cadence ring_restart; do "$build/sim_fault" "$s" "$log" || fail=1; done
    fi

    # The colour path (colour.c): QMK's own conversion and CIE table in place
    # of sim.c's stub, and the board's DRIFT and RAINFALL under the ceilings.
    if [ -f "$build/rgb_matrix_kb.inc" ] && grep -q 'want_val' "$build/power.c"; then
        for f in color led_tables; do
            cc -std=c11 -O1 -Wall -DUSE_CIE1931_CURVE -I"$qroot/quantum" -I"$qroot/platforms" \
               -c -o "$build/$f.o" "$qroot/quantum/$f.c"
        done
        colour() {   # colour <out> <dir holding rgb_matrix_kb.inc>
            cc -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -DSIM_REAL_COLOUR \
               -I"$2" -I"$build" -idirafter "$qroot/quantum" -o "$1" "$here/sim.c" "$build/battery.c" \
               "$build/power.c" "$build/color.o" "$build/led_tables.o" -lm
        }
        colour "$build/sim_colour" "$build"
        for s in k_hook k_drift k_drift_usb k_rainfall; do
            "$build/sim_colour" "$s" || fail=1
        done
        # k_drift_usb's hash is DRIFT's before the revision (8b06e4dcc4): that
        # DRIFT, built here beside today's power.c, must give it too, or the
        # constant is not what it claims to be.
        base="$build/drift-8b06e4dcc4"
        mkdir -p "$base"
        if git -C "$qroot" show 8b06e4dcc4:keyboards/a_jazz/ak820pro/rgb_matrix_kb.inc > "$base/rgb_matrix_kb.inc" 2>/dev/null; then
            colour "$base/sim_colour" "$base"
            "$base/sim_colour" k_drift_usb > "$base/out.txt" || { cat "$base/out.txt"; echo "FAIL 8b06e4dcc4's DRIFT does not give k_drift_usb's hash"; fail=1; }
            grep -q '^ok' "$base/out.txt" && echo "ok   k_drift_usb's hash is 8b06e4dcc4's DRIFT's"
        else
            echo "FAIL 8b06e4dcc4 not in $qroot: k_drift_usb's hash unchecked"; fail=1
        fi
    fi
fi

# The mutants (mutants.py): each a change to a copy of the source that a named
# scenario must catch. `run.sh --no-mutants` skips them.
if [ "${1:-}" != "--no-mutants" ] && grep -q 'want_val' "$build/power.c"; then
    python3 "$here/mutants.py" --src "$kb" || fail=1
fi

# Phase 2's sensitivity (report only, `run.sh --sensitivity`): both drains
# replayed with the capacity wrong by -13, -5, +5 and +13%. A wrong capacity
# is a wrong count, so this is the gauge's answer to a pack that has aged or a
# model that is off; the plan reports it, it does not gate on it.
if [ "${1:-}" = "--sensitivity" ] && grep -q '^#define POWER_HAS_MODES' "$build/power.h"; then
    for e in 13554 14800 16358 17604; do
        cc -std=c11 -O1 -w -DE_CAP_MWH=${e}u -I"$build" -o "$build/sim_$e" "$here/sim.c" "$build/battery.c" "$build/power.c" -lm
        echo "--- capacity $e mWh (true 15579)"
        "$build/sim_$e" c_replay_r3 "$hist/battery-2026-10-15-drain-2f/log-20261018-0205-rgbcut.csv" | grep -E 'worst|^ok' || true
        "$build/sim_$e" c_replay_2e "$hist/battery-2026-10-12-drain-2e/log-20261014-0950-preswap.csv" | grep -E 'worst|^ok' || true
    done
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
