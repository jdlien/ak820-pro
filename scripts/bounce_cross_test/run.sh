#!/usr/bin/env bash
# The cancel-pairing bounce only for the advertising slot's own key
# (plans/AUDIT-2026-10-31.md, F-022; first written as the audit's verify-001).
# The real bt_ui.c and bluetooth/ch582f_ajazz.c, by path, with a module model
# built from docs/wireless.md: nine cases (advertising on each slot, a tap on
# each), then the same with the advertising window expired. While advertising
# every case must be as documented: a different slot's tap a plain select,
# the same slot's a bounce. Expired, the cross-slot taps are plain selects
# too; the same slot's three still bounce (+700 ms), since the end of an
# advertising window is never observed (F-003) and conn_state stays PAIRING.
# CC picks the compiler (default cc); SAN the sanitizer flags.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -g -O1 $san -Wall -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable \
    -I"$here/stubs" -I"$kb" -I"$kb/bluetooth" -o "$o/t" "$here/t_bounce_cross.c" "$kb/bt_ui.c" "$kb/bluetooth/ch582f_ajazz.c"
a="$("$o/t" | grep '^SUMMARY')"; e="$("$o/t" --expired | grep '^SUMMARY')"
echo "advertising: $a"; echo "expired:     $e"
x0="0 cross-slot bounces through the advertising slot (+700 ms), 0 cross-slot bounces through an unrelated third slot"
[[ "$a" == "SUMMARY: 9 as documented"*"$x0" && "$e" == "SUMMARY: 6 as documented"*"$x0" ]] || { echo "RESULT: FAIL"; exit 1; }
echo "RESULT: PASS"
