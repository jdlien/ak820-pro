#!/usr/bin/env bash
# The real sleep.c, power.c and both timer.c files (by path, unedited) against
# the stubs here, with the 64-bit timer conversions counted per main-loop pass
# (plans/AUDIT-2026-10-31.md, F-027; first written as the audit's verify-011).
# CC picks the compiler (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=all}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -O1 -g $san -Wall -Wno-unknown-attributes -Wno-include-next-absolute-path -Wno-invalid-noreturn \
    -DPARAM_OVERLAY '-Dsection(x)=used' -I"$here/stubs" -I"$q/platforms" -I"$q/platforms/chibios" -I"$kb" \
    -o "$o/test" "$here/test.c" "$here/stubs.c" "$kb/sleep.c" "$kb/power.c" "$q/platforms/chibios/timer.c" "$q/platforms/timer.c"
"$o/test"
