/* Host stand-in for QMK's quantum.h: the clock and string functions. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
uint32_t timer_read32(void);
