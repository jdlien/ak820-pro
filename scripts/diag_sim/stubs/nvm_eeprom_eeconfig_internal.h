/* Host stand-in: the offsets the real header derives from eeprom_core_t
 * (quantum/nvm/eeprom/nvm_eeprom_eeconfig_internal.h), as this board builds
 * it: core 37 bytes, rgb_matrix at 23 (packed), the kb datablock at 37 (9
 * bytes since the menu's P2a, 2026-10-25; -DEECONFIG_KB_DATA_SIZE=7 builds
 * an older flash_stats.c, run.sh's comparison of the old pages). */
#pragma once
#include <stdint.h>
#ifndef EECONFIG_KB_DATA_SIZE
#    define EECONFIG_KB_DATA_SIZE 9
#endif
#define EECONFIG_RGB_MATRIX ((uint64_t *)23)
#define EECONFIG_KB_DATABLOCK ((uint8_t *)37)
#define EECONFIG_SIZE (37 + EECONFIG_KB_DATA_SIZE)
