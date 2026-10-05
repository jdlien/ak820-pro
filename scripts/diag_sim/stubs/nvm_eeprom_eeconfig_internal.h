/* Host stand-in: the offsets the real header derives from eeprom_core_t
 * (quantum/nvm/eeprom/nvm_eeprom_eeconfig_internal.h), as this board builds
 * it: core 37 bytes, rgb_matrix at 23 (packed), the kb datablock (6 bytes) at 37. */
#pragma once
#include <stdint.h>
#define EECONFIG_KB_DATA_SIZE 6
#define EECONFIG_RGB_MATRIX ((uint64_t *)23)
#define EECONFIG_KB_DATABLOCK ((uint8_t *)37)
#define EECONFIG_SIZE (37 + 6)
