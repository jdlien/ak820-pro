#!/usr/bin/env bash
# The battery gauge's ratchet never raises the level on battery
# (plans/AUDIT-2026-10-31.md, F-021): battery.c and power.c copied verbatim
# beside scripts/battery_sim's stubs. CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
cp -R "$here/../battery_sim/stubs/." "$o/"
cp "$kb/battery.c" "$kb/battery.h" "$kb/battery_tail.h" "$kb/power.c" "$kb/power.h" "$o/"
# shellcheck disable=SC2086
"$cc" -g -O1 -std=gnu11 $san -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -I"$o" \
    -o "$o/test" "$here/test.c" "$o/power.c"
"$o/test" > "$o/out.txt" 2>&1 || { tail -20 "$o/out.txt"; exit 1; }
tail -1 "$o/out.txt"
