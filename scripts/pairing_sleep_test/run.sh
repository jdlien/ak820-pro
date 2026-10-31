#!/usr/bin/env bash
# The real ch582f_ajazz.c, bt_ui.c and sleep.c, compiled by path from the
# firmware tree, against the stubs and the module model here; runs test.c's
# five scenarios for an hour each. sleep.c's .ramtext section attribute is
# ELF-only; -D'section(x)=__used__' turns it into a plain attribute on Mach-O
# (a command-line macro, not an edit). CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kb="$here/../../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer}"
w="-std=gnu11 -g -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -Wno-unknown-attributes"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
{
  "$cc" $san $w -I"$here/stubs_radio" -I"$kb/bluetooth" -I"$kb" -c "$kb/bluetooth/ch582f_ajazz.c" -o "$o/ch582f_ajazz.o"
  "$cc" $san $w -I"$here/stubs_radio" -c "$here/world_radio.c" -o "$o/world_radio.o"
  "$cc" $san $w -I"$here/stubs_sys" -I"$kb" -c "$kb/bt_ui.c" -o "$o/bt_ui.o"
  "$cc" $san $w "-Dsection(x)=__used__" -Wno-unused-but-set-global -Wno-unknown-warning-option -I"$here/stubs_sys" -I"$kb" -c "$kb/sleep.c" -o "$o/sleep.o"
  "$cc" $san $w -I"$here/stubs_sys" -I"$kb" -c "$here/world_sys.c" -o "$o/world_sys.o"
  "$cc" $san $w -I"$here/stubs_sys" -I"$kb" -c "$here/test.c" -o "$o/test.o"
  "$cc" $san -o "$o/test" "$o"/*.o
}
fails=0
for s in A B C D E; do "$o/test" "$s" 60 | grep -E '^(scenario|RESULT|FAIL)' || fails=1; done
exit $fails
