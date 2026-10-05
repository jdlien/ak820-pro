/* Host stand-in for QMK's quantum.h: timers (simulated) and printf. */
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
