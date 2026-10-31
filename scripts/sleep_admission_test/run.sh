#!/usr/bin/env bash
# The real sleep.c and bluetooth/ch582f_ajazz.c (by path, unedited) against
# the stubs here, with the UART2 ISR's queue writes modelled: frames the radio
# sends inside the pass that sleeps (plans/AUDIT-2026-10-31.md, F-020; first
# written as the audit's verify-032). CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer}"
fl="-std=gnu11 -g -O1 $san -Wall -Wno-unknown-attributes -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unknown-warning-option"
inc="-I$here/stubs -I$kb -I$q/drivers/bluetooth -I$q/tmk_core/protocol -I$q/quantum"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
{
  "$cc" $fl $inc -c "$kb/sleep.c" -o "$o/sleep.o"
  "$cc" $fl $inc -c "$kb/bluetooth/ch582f_ajazz.c" -o "$o/ch582.o"
  "$cc" $fl $inc -c "$here/stubs.c" -o "$o/stubs.o"
  "$cc" $fl $inc -c "$here/test.c" -o "$o/test.o"
  "$cc" $san -o "$o/test" "$o/test.o" "$o/sleep.o" "$o/ch582.o" "$o/stubs.o"
}
"$o/test"
