#!/usr/bin/env bash
# Build the firmware's CH582F driver, verbatim, against the stubs here and run
# every case in harness.c (Phase 1b, D1: the transport counters). Built with
# the daily flavor's flags: RAW_ENABLE, and neither CONSOLE_ENABLE nor
# WDT_TEST_HOOKS -- the counters must exist where the soaks run.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="${CH582_SIM_SRC:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/bluetooth}"   # override to test a mutant
kb="${CH582_SIM_KB:-$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro}"   # bt_ui.c's (btui.c)
cc="${CC:-cc}"
py="${PYTHON:-python3}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$here/stubs/." "$build/"
cp "$src/ch582f_ajazz.c" "$src/ch582f_ajazz.h" "$build/"
"$cc" -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -DRAW_ENABLE -I"$build" \
   -o "$build/harness" "$here/harness.c" "$build/ch582f_ajazz.c"
# P3: bt_ui.c's menu calls on the driver (btui.c), both verbatim, in a tree of
# their own: stubs_btui/ over stubs/, the driver's header where bt_ui.c finds it.
bt="$build/btui_src"
mkdir -p "$bt/bluetooth"
cp -R "$here/stubs/." "$bt/"
cp -R "$here/stubs_btui/." "$bt/"
cp "$src/ch582f_ajazz.c" "$src/ch582f_ajazz.h" "$bt/"
cp "$src/ch582f_ajazz.h" "$bt/bluetooth/"
cp "$kb/bt_ui.c" "$kb/bt_ui.h" "$bt/"
"$cc" -std=c11 -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -DRAW_ENABLE -I"$bt" -I"$here" \
   -o "$build/btui" "$here/btui.c" "$bt/ch582f_ajazz.c" "$bt/bt_ui.c"
fail=0
for c in withheld queue_full replaced not_replaced_none_behind not_replaced_head uart_errors; do
    "$build/harness" "$c" || fail=1
done
for c in tap_select pair_current_linked pair_other_rejected pair_other_cap pair_other_oldhost pair_bounce \
         pair_lost_select pair_superseded pair_lost_confirm pair_promotion stop_cases already_advertising \
         bounce_stale bounce_lost last_try_window direct_36 boot_retry_pending hold_superseded \
         target_given_up target_refused; do
    "$build/btui" "$c" || fail=1
done
# D2's profile (flash 1c): the C case, then hostagent/ak820health.py's own
# decoder over the pages the driver filled.
"$build/harness" profile > "$build/profile.out" || fail=1
grep -v '^PAGE ' "$build/profile.out"
"$py" "$here/test_prof_decode.py" < "$build/profile.out" || fail=1
exit $fail
