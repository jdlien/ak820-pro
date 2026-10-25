/* Host stand-in for QMK's quantum.h, for kb_eeconfig.c (kbee.c): the clock,
 * the kb datablock's read and update, and the block's size (config.h's,
 * through the EEPROM layout stub). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "nvm_eeprom_eeconfig_internal.h"
uint32_t timer_read32(void);
static inline uint32_t timer_elapsed32(uint32_t t) { return timer_read32() - t; }
uint32_t eeconfig_read_kb_datablock(void *data, uint32_t offset, uint32_t length);
uint32_t eeconfig_update_kb_datablock(const void *data, uint32_t offset, uint32_t length);
