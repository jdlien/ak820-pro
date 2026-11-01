#pragma once
/* Host stub of quantum.h for bt_ui.c, ch582f_ajazz.c and the extracted
 * dip_switch_update_kb(). */
#include "hal.h"
#include <stdint.h>
#include <stdbool.h>
uint16_t timer_read(void);
uint32_t timer_read32(void);
uint16_t timer_elapsed(uint16_t t);
uint32_t timer_elapsed32(uint32_t t);
typedef struct { struct { bool pressed; } event; } keyrecord_t;
void clear_keyboard(void);
#define QK_KB_0 0x7E00
#define printf(...) ((void)0)
