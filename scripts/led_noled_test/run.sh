#!/usr/bin/env bash
# The real drivers/led/sn32f2xx.c (#included by test.c) at the board's 9 empty
# matrix cells: the row ISR must never read led_state[NO_LED], and a dark frame
# must energise no mux row (plans/AUDIT-2026-10-31.md, F-033). UBSan's bounds
# check fails the run on the read itself. CC picks the compiler (default cc);
# SAN the sanitizer flags.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -g -O0 $san -include "$here/stubs/config.h" -I"$here/stubs" -I"$q/drivers/led" \
    -DFW_LED_C="\"$q/drivers/led/sn32f2xx.c\"" "$here/test.c" -o "$o/test"
"$o/test"
