#!/usr/bin/env bash
# The real rtc/rtc.c, the SN32 RTC LLD and ChibiOS's hal_rtc.c (by path,
# unedited) against the stubs and the hardware model here: a step whose
# locked section meets the second match (plans/AUDIT-2026-10-31.md, F-025).
# CC picks the compiler (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable \
    -I"$here/stubs" -I"$kb" -I"$kb/rtc" -I"$q/lib/chibios/os/hal/include" \
    -I"$q/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC" \
    -DRTC_AUTO_CALIBRATION -DRTC_CHECK_INTERVAL_S=60 -DRTC_PERIOD_INITIAL=33600 \
    -o "$o/test" "$here/test.c" "$here/hw_model.c" "$kb/rtc/rtc.c" \
    "$q/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC/hal_rtc_lld.c" "$q/lib/chibios/os/hal/src/hal_rtc.c"
"$o/test"
