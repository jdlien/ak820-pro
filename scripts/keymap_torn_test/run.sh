#!/usr/bin/env bash
# The real quantum/nvm/eeprom/nvm_dynamic_keymap.c (#included by test.c), the
# EEPROM driver and quantum/wear_leveling/wear_leveling.c over a model of the
# SN32's 8-byte-line flash, cut cleanly at every program or erase
# (plans/AUDIT-2026-10-31.md, F-017). CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
# shellcheck disable=SC2086
"$cc" -g -O1 $san -Wno-pointer-arith -Wno-gnu-pointer-arith -Wno-int-to-void-pointer-cast -Wno-pointer-to-int-cast \
    -DEEPROM_DRIVER -DEEPROM_WEAR_LEVELING -DWEAR_LEVELING_EMBEDDED_FLASH -DNVM_DRIVER_EEPROM \
    -DVIA_ENABLE -DENCODER_ENABLE -DENCODER_MAP_ENABLE -DDYNAMIC_KEYMAP_ENABLE \
    -DMATRIX_ROWS=6 -DMATRIX_COLS=15 -DDYNAMIC_KEYMAP_LAYER_COUNT=4 \
    -DEECONFIG_KB_DATA_SIZE=10 -DDYNAMIC_KEYMAP_MACRO_EEPROM_SIZE=19 \
    -I"$here/stubs" -I"$q/quantum/nvm/eeprom" -I"$q/quantum" -I"$q/quantum/nvm" -I"$q/platforms" \
    -I"$q/quantum/wear_leveling" -I"$q/drivers/eeprom" -I"$q/lib/fnv" \
    "$here/test.c" "$q/drivers/eeprom/eeprom_driver.c" "$q/drivers/eeprom/eeprom_wear_leveling.c" \
    "$q/quantum/wear_leveling/wear_leveling.c" "$q/lib/fnv/hash_64a.c" -o "$o/test"
"$o/test"
