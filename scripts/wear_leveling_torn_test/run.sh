#!/usr/bin/env bash
# The real quantum/wear_leveling/wear_leveling.c, the EFL backing store, the
# EEPROM driver, nvm_eeconfig.c and the board's kb_eeconfig.c over a model of
# the SN32's 8-byte-line flash, each program cut at a chosen bit pattern
# (plans/AUDIT-2026-10-31.md, F-010). CC picks the compiler (default cc); SAN
# the sanitizer flags (SAN= for none).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
q="$here/../../qmk_firmware-ak820pro"
k="$q/keyboards/a_jazz/ak820pro"
cc="${CC:-cc}"
san="${SAN--fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer}"
o="$(mktemp -d)"
trap 'rm -rf "$o"' EXIT
defs="-DQMK_MCU_FAMILY_SN32 -DQMK_MCU_SERIES_SN32F290 -DEEPROM_DRIVER -DEEPROM_WEAR_LEVELING -DWEAR_LEVELING_EMBEDDED_FLASH
      -DRGB_MATRIX_ENABLE -DMATRIX_ROWS=6 -DMATRIX_COLS=16 -DRGB_MATRIX_LED_COUNT=82
      -DEECONFIG_KB_DATA_SIZE=10 -DEECONFIG_KB_DATA_VERSION=7 -DEECONFIG_USER_DATA_SIZE=0"
inc="-I$here/stubs -I$q/platforms/chibios/drivers -I$q/platforms/chibios/drivers/wear_leveling -I$q/quantum/wear_leveling
     -I$q/lib/fnv -I$q/quantum -I$q/quantum/nvm -I$q/quantum/nvm/eeprom -I$q/quantum/logging -I$q/platforms
     -I$q/drivers/eeprom -I$q/quantum/rgb_matrix -I$q/tmk_core/protocol -I$k"
# shellcheck disable=SC2086
"$cc" -std=gnu11 -g -O1 $san -Wall -Wextra -Wno-unused-parameter $defs $inc -o "$o/test" "$here/test.c" \
    "$q/quantum/wear_leveling/wear_leveling.c" "$q/platforms/chibios/drivers/wear_leveling/wear_leveling_efl.c" \
    "$q/lib/fnv/hash_64a.c" "$q/drivers/eeprom/eeprom_driver.c" "$q/drivers/eeprom/eeprom_wear_leveling.c" \
    "$q/quantum/nvm/eeprom/nvm_eeconfig.c" "$k/kb_eeconfig.c"
"$o/test"
