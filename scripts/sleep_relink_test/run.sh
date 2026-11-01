#!/usr/bin/env bash
# A link that comes up while the board deep-sleeps (plans/AUDIT-2026-10-31.md,
# F-023; the audit's verify-003). The real bluetooth/ch582f_ajazz.c, #included
# by fw_unit.c, with the audit's UART/peer/clock model (scripts/ch582_link_model) and the deep
# sleep sequenced as sleep.c does it. Mach-O only: the driver's statics are
# reset between scenarios through its own sections (getsectiondata). CC picks
# the compiler (default cc); SAN the sanitizer flags.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -g -O1 $san -std=gnu11 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -I"$here/../ch582_link_model/stubs" -I"$kb" -I"$kb/bluetooth" \
    -I"$here" -I"$here/../ch582_link_model" -DRAW_ENABLE -DVIA_ENABLE -DFW_CH582_C="\"$kb/bluetooth/ch582f_ajazz.c\"" \
    -o "$o/t" "$here/fw_unit.c" "$here/../ch582_link_model/sim.c" "$here/test_sleep_relink.c"
"$o/t"
