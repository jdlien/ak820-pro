#pragma once
#include "hal.h"
uint16_t timer_read(void);
uint32_t timer_read32(void);
uint16_t timer_elapsed(uint16_t t);
uint32_t timer_elapsed32(uint32_t t);
/* bt_ui.c's needs (QMK types, cut down) */
#define QK_KB_0 0x7E00
typedef struct { bool pressed; } keyevent_t;
typedef struct { keyevent_t event; } keyrecord_t;
void clear_keyboard(void);
#define printf(...) ((void)0)
