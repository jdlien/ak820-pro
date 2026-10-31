#pragma once
#include "hal.h"
uint16_t timer_read(void);
uint32_t timer_read32(void);
uint16_t timer_elapsed(uint16_t t);
uint32_t timer_elapsed32(uint32_t t);
#define printf(...) ((void)0)
