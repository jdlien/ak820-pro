/* The stubs' quantum.h (stubs/quantum.h), plus what bt_ui.c uses: a key
 * record and clear_keyboard(). For btui.c (P3); copied over stubs/'s. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "report.h"
uint16_t timer_read(void);
uint16_t timer_elapsed(uint16_t last);
uint32_t timer_read32(void);
uint32_t timer_elapsed32(uint32_t last);
typedef struct { bool pressed; } keyevent_t;
typedef struct { keyevent_t event; } keyrecord_t;
void clear_keyboard(void);
