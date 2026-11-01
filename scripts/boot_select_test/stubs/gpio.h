#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t pin_t;
enum { B1 = 0, B12 = 1, B13 = 2 };
void gpio_set_pin_input_high(pin_t p);
bool gpio_read_pin(pin_t p);   /* true = high = inactive (dip_switch.c inverts) */
