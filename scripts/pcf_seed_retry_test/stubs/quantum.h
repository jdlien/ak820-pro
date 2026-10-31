/* Host stand-in for QMK's quantum.h: what rtc.c and ak820pro.h use. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#ifndef MIN
#    define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef MAX
#    define MAX(a, b) ((a) > (b) ? (a) : (b))
#endif

/* QMK pin names used as the I2C lines' defaults. */
#define A14 14
#define A15 15

#define QK_KB_0 0x7E00

uint32_t timer_read32(void);
uint32_t last_input_activity_elapsed(void);
