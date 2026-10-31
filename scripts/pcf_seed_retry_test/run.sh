#!/usr/bin/env bash
# The real rtc/rtc.c (by path, unedited) against the software SN32 RTC, the
# PCF8563 model and the main loop here (plans/AUDIT-2026-10-31.md, F-006):
# the control, then a boot whose first PCF transaction fails. config.h's RTC
# values. CC picks the compiler (default cc); SAN the sanitizer flags (SAN=
# for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -Wno-sign-compare \
    -Wno-missing-field-initializers -DRTC_AUTO_CALIBRATION -DRTC_CHECK_INTERVAL_S=60 -DRTC_PERIOD_INITIAL=33600 \
    -I"$here/stubs" -I"$kb" -I"$kb/rtc" -o "$o/test" "$here/test.c" "$kb/rtc/rtc.c"
fails=0
for m in control first stopped sleepfirst; do
  "$o/test" "$m" | grep -E '^==|FAIL|PASSED' || fails=1
done
exit $fails
