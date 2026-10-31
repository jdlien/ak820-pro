/* Host stand-in for QMK's quantum.h, for sleep.c and bt_ui.c only. */
#pragma once
#include "hal.h"
typedef uint16_t matrix_row_t;
matrix_row_t matrix_get_row(uint8_t row);
uint16_t timer_read(void);
uint32_t timer_read32(void);
uint16_t timer_elapsed(uint16_t t);
uint32_t timer_elapsed32(uint32_t t);
uint32_t last_input_activity_elapsed(void);
uint32_t last_encoder_activity_time(void);
typedef struct { struct { uint8_t col, row; } key; bool pressed; uint16_t time; } keyevent_t;
typedef struct { keyevent_t event; } keyrecord_t;
void clear_keyboard(void);
#define QK_KB_0 0x7E00
