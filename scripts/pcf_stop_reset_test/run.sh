#!/usr/bin/env bash
# The real rtc/rtc.c, the real SN32 RTC LLD and ChibiOS's hal_rtc.c (by path,
# unedited) against the stubs and the PCF8563 model here, through an MCU
# reset inside a write run's STOP window (plans/AUDIT-2026-10-31.md, F-005),
# and the control, a reset after it. config.h's RTC values; a daily build (no
# dev hooks). CC picks the compiler (default cc); SAN the sanitizer flags
# (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
chi="$q/lib/chibios/os/hal"
lld="$q/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
fl="-std=gnu11 -g -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function $san
    -I$here/stubs -I$kb -I$chi/include -I$lld
    -DRTC_AUTO_CALIBRATION -DRTC_CHECK_INTERVAL_S=60 -DRTC_PERIOD_INITIAL=33600"
# shellcheck disable=SC2086
{
  "$cc" $fl -c "$kb/rtc/rtc.c" -o "$o/rtc.o"
  "$cc" $fl -c "$lld/hal_rtc_lld.c" -o "$o/hal_rtc_lld.o"
  "$cc" $fl -c "$chi/src/hal_rtc.c" -o "$o/hal_rtc.o"
  "$cc" $fl -c "$here/test.c" -o "$o/test.o"
  "$cc" $fl "$o/rtc.o" "$o/hal_rtc_lld.o" "$o/hal_rtc.o" "$o/test.o" -o "$o/test"
}
fails=0
for m in stuck control; do
  echo "== $m"
  "$o/test" "$m" | grep -E '^  (ok|FAIL)|^RESULT' || fails=1
done
exit $fails
