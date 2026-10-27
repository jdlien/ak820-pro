/* flash_tidy_test's stand-in: what flash_tidy.c takes from QMK (test.c fakes). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
uint32_t last_input_activity_elapsed(void);
uint32_t last_input_activity_time(void);
uint32_t timer_read32(void);
