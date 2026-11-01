/* Host stand-in for QMK's quantum.h: the millisecond timer (sim.c, derived
 * from the same tick as the system time), wait_ms, and printf, which without
 * CONSOLE_ENABLE prints nothing on the board. */
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
void     wait_ms(uint32_t ms);
static inline void fw_printf_(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static inline void fw_printf_(const char *fmt, ...) { (void)fmt; }
#define printf(...) fw_printf_(__VA_ARGS__)
