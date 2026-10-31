#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include "hal.h"
#define QK_KB_0 0x7E00
uint32_t last_input_activity_elapsed(void);
#define A14 14
#define A15 15
#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef MAX
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#endif
#define wait_us(us) ((void)(us))
/* QMK's printf goes to the console; quiet here unless asked. */
#ifdef VERIFY_PRINT
#else
#define printf(...) ((void)0)
#endif
