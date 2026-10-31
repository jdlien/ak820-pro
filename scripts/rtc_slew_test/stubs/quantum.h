#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include "hal.h"
#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef MAX
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#endif
#define A14 14
#define A15 15
uint32_t timer_read32(void);
uint32_t timer_elapsed32(uint32_t t);
void wait_us(uint32_t us);
#include <string.h>
#define QK_KB_0 0x7E00
uint32_t last_input_activity_elapsed(void);
