#!/usr/bin/env bash
# rtc_apply_bytes(), extracted verbatim from hid_protocol.c, with
# rtc/rtc_payload.h's rtc_days_in_month(); runs test.c's sweep of every date
# byte (plans/AUDIT-2026-10-31.md, F-016). CC picks the compiler (default
# cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
# From the first line matching $2 through the next line that is "}".
extract() { RE="$2" awk 'f==0 && $0 ~ ENVIRON["RE"] {f=1} f==1 {print} f==1 && $0=="}" {exit}' "$1"; }
extract "$kb/hid_protocol.c" '^static bool rtc_apply_bytes\(const uint8_t \*p\) \{$' > "$build/x_apply.inc"
extract "$kb/rtc/rtc_payload.h" '^static inline uint8_t rtc_days_in_month\(uint16_t year, uint8_t mo\) \{$' > "$build/rtc_payload_month.inc"
[[ -s "$build/x_apply.inc" && -s "$build/rtc_payload_month.inc" ]] || { echo "FAIL: a function was not found" >&2; exit 1; }
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g -Wall -Wextra $san -I"$build" -o "$build/test" "$here/test.c"
"$build/test"
