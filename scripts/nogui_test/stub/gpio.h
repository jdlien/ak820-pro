/* Stub gpio.h: the dip switch pins read from a fake level table. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t pin_t;
extern bool fake_pin_level[64];
static inline void gpio_set_pin_input_high(pin_t p) { (void)p; }
static inline bool gpio_read_pin(pin_t p) { return fake_pin_level[p]; }
