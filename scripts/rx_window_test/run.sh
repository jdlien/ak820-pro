#!/usr/bin/env bash
# A partial frame left in the parser's 3-byte window no longer swallows the
# module's next frame (plans/AUDIT-2026-10-31.md, F-019; first written as the
# audit's verify-043). The real bluetooth/ch582f_ajazz.c (#included by
# unit.c), daily and dev, driven through bluetooth_task() with the audit's link
# model (scripts/ch582_link_model). Eleven scenarios each: a lost checksum
# then 5B 33 or 5B 36, a stale 5A 07 then a key report, and the controls.
# Every one must end as a correct driver would. CC picks the compiler
# (default cc); SAN the sanitizer flags.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
m="$here/../ch582_link_model"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
common="-std=gnu11 -g -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -I$m/stubs -I$kb -I$kb/bluetooth -I$m -DRAW_ENABLE -DVIA_ENABLE"
fails=0
for flavour in daily dev; do
    defs="" extra=""
    if [[ $flavour == dev ]]; then defs="-DAK820_DEV_HOOKS"; extra="$kb/bluetooth/raw81.c $kb/lockchan.c $kb/lockchan_media.c"; fi
    # shellcheck disable=SC2086
    "$cc" $san $common $defs -DFW_CH582_C="\"$kb/bluetooth/ch582f_ajazz.c\"" -o "$o/$flavour" "$here/unit.c" "$m/sim.c" "$here/test.c" $extra
    out="$("$o/$flavour")" || true
    line="$(echo "$out" | grep '^== ')"
    echo "$flavour: ${line#== }"
    [[ "$line" == "== 0 scenario(s) not as a correct driver would leave them" ]] || { echo "$out" | grep -B2 WRONG; fails=1; }
done
[[ $fails -eq 0 ]] && echo "RESULT: PASS" || { echo "RESULT: FAIL"; exit 1; }
