#!/usr/bin/env bash
# The real rtc/rtc.c, compiled into test.c by #include, against the stubs and
# the SN32 RTC model here: a slew's error at each latency
# (plans/AUDIT-2026-10-31.md, F-026). CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable \
    -I"$here/stubs" -I"$kb" -I"$kb/rtc" -o "$o/test" "$here/test.c"
"$o/test"
