/* Host stand-in for QMK's quantum.h (verify-018). */
#pragma once
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "hal.h"
#define QK_KB_0 0x7E00
#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
uint32_t last_input_activity_elapsed(void);
uint32_t timer_read32(void);
