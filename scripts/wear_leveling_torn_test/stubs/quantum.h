/* Host stand-in for QMK's quantum.h, for kb_eeconfig.c compiled by path: the
 * clock and the kb datablock's read/update, routed to QMK's real
 * nvm_eeconfig.c in the test build. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
uint32_t timer_read32(void);
static inline uint32_t timer_elapsed32(uint32_t t) { return timer_read32() - t; }
uint32_t eeconfig_read_kb_datablock(void *data, uint32_t offset, uint32_t length);
uint32_t eeconfig_update_kb_datablock(const void *data, uint32_t offset, uint32_t length);
