#!/usr/bin/env bash
# A key report queued behind a select never coalesces into a frame before it
# (plans/AUDIT-2026-10-31.md, F-013; first written as the audit's verify-044).
# The real bluetooth/ch582f_ajazz.c (daily), #included by the test, with a
# module that ACKs after 5 ms except during a stall: 20 frames queued on slot
# 1, then Fn+W, then a key 0-200 ms later. The key must go out after the
# select, on slot 2's link, and slot 1's host be left with nothing held; the
# control queues the select behind 3 frames. CC picks the compiler (default
# cc); SAN the sanitizer flags.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wno-unused-function -Wno-unused-parameter -I"$here/stubs" -I"$kb" -I"$kb/bluetooth" \
    -DRAW_ENABLE -DFW_CH582_C="\"$kb/bluetooth/ch582f_ajazz.c\"" -o "$o/t" "$here/test_coalesce_select.c"
fails=0
check() {   # label, then the command's environment and arguments
    local label="$1"; shift
    local r; r="$(env "$@" | grep 'RESULT')"
    echo "$label: ${r#*RESULT: }"
    [[ "$r" == *"RESULT: ok"* ]] || fails=1
}
check "control (select behind 3 frames)" "$o/t" control
for d in 0 50 100 150 200; do check "20 queued, the key ${d} ms after the select" A_DELAY_MS=$d "$o/t"; done
[[ $fails -eq 0 ]] && echo "RESULT: PASS" || { echo "RESULT: FAIL"; exit 1; }
