#!/usr/bin/env bash
# The Win/Mac switch's GUI lock (plans/AUDIT-2026-10-31.md, F-029): the VIA
# keymap's dip_switch_update_user(), QMK's process_magic.c, keycode_config.c
# and dip_switch.c compiled by path, with a fake EEPROM and switch pin. CC
# picks the compiler (default cc); SAN the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
kb="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -DMAGIC_ENABLE -DDIP_SWITCH_ENABLE "-DDIP_SWITCH_PINS={1,12,13}" \
    '-DQMK_KEYBOARD_H="kb_stub.h"' -I"$here/stub" -I"$kb" -I"$q/quantum" -I"$q/quantum/keymap_extras" \
    -I"$q/quantum/sequencer" -I"$q/platforms" -o "$o/test" \
    "$here/test.c" "$kb/keymaps/via/keymap.c" "$q/quantum/process_keycode/process_magic.c" \
    "$q/quantum/keycode_config.c" "$q/quantum/dip_switch.c"
"$o/test" > "$o/out.txt" || { cat "$o/out.txt"; exit 1; }
tail -1 "$o/out.txt"
