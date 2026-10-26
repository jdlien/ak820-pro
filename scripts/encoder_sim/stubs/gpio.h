/* Host stand-in for platforms/gpio.h: the knob's two pins. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t pin_t;
#define NO_PIN 0xFFu
#define B2 1
#define A10 2
void gpio_set_pin_input_high(pin_t pin);
bool gpio_read_pin(pin_t pin);
