#!/usr/bin/env bash
# RTC_GET_TIME's reply from one stamp (plans/AUDIT-2026-10-31.md, F-009). Builds
# the real hal_rtc_lld.c and ChibiOS's hal_rtc.c whole, and extracts rtc.c's
# stamp and page-1 code and hid_protocol.c's rtc_read_into() verbatim, with
# ak820ctl.c's board_sod(); runs a GET at every microsecond of a second. CC
# picks the compiler (default cc); SAN the sanitizer flags (SAN= for none).
# Usage: run.sh [decode_us ...] (default 300 150)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$here/../.."
qmk="$repo/qmk_firmware-ak820pro"
kb="$qmk/keyboards/a_jazz/ak820pro"
lld="$qmk/lib/chibios-contrib/os/hal/ports/SN32/LLD/SN32F2xx/RTC"
chi="$qmk/lib/chibios/os/hal"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

# From the first line matching $2 through the next line that is "}".
extract() { RE="$2" awk 'f==0 && $0 ~ ENVIRON["RE"] {f=1} f==1 {print} f==1 && $0=="}" {exit}' "$1"; }
need() { [[ -n "$1" ]] || { echo "FAIL: $2 not found in the source" >&2; exit 1; }; echo "$1"; }
{
  need "$(extract "$kb/rtc/rtc.c" '^static void chibiostime_to_rtc\(const RTCDateTime \*src,')" chibiostime_to_rtc
  need "$(extract "$kb/rtc/rtc.c" '^bool rtc_get_time\(rtc_time_t \*out\)$')" rtc_get_time
  need "$(extract "$kb/rtc/rtc.c" '^bool rtc_now\(rtc_stamp_t \*s\)$')" rtc_now
  need "$(grep -m1 -E '^static void put16\(uint8_t \*p, uint16_t v\)' "$kb/rtc/rtc.c")" put16
  need "$(grep -m1 -E '^static void put32\(uint8_t \*p, uint32_t v\)' "$kb/rtc/rtc.c")" put32
  need "$(extract "$kb/rtc/rtc.c" '^void rtc_status_fill_page1\(const rtc_stamp_t \*s, uint8_t \*out\)$')" rtc_status_fill_page1
  need "$(extract "$kb/rtc/rtc.c" '^void rtc_status_fill\(uint8_t page, uint8_t \*out\)$')" rtc_status_fill
} > "$build/x_rtc.inc"
need "$(extract "$kb/hid_protocol.c" '^static void rtc_read_into\(uint8_t \*data\) \{$')" rtc_read_into > "$build/x_hid_protocol.inc"
need "$(extract "$repo/time-util-ak820pro/ak820ctl.c" '^static double board_sod\(const unsigned char \*rep\) \{$')" board_sod > "$build/x_ak820ctl.inc"

flags="-std=gnu11 -O1 -g -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -Wno-unused-variable $san"
inc="-I$here/stubs -I$chi/include -I$lld -I$kb/rtc -I$build"
# shellcheck disable=SC2086
{
  "$cc" $flags $inc -Dlocaltime_r=sim_localtime_r -c "$lld/hal_rtc_lld.c" -o "$build/hal_rtc_lld.o"
  "$cc" $flags $inc -c "$chi/src/hal_rtc.c" -o "$build/hal_rtc.o"
  "$cc" $flags $inc -c "$here/test.c" -o "$build/test.o"
  "$cc" $san "$build/test.o" "$build/hal_rtc_lld.o" "$build/hal_rtc.o" -o "$build/test"
}
[[ $# -gt 0 ]] || set -- 300 150
for d in "$@"; do "$build/test" "$d"; done
