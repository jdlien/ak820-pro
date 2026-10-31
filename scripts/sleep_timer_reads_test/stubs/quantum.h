/* Host stub of the QMK surface sleep.c and power.c use. timer.h is QMK's
 * real one (platforms/timer.h); the timer is QMK's real chibios timer.c. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "timer.h"
#include "ch.h"
#include "hal.h"
typedef uint32_t pin_t;
typedef uint32_t ioportid_t;
#define PAL_PORT(p) ((p) >> 5)
#define PAL_PAD(p)  ((p) & 31u)
#define A0 (0u << 5)
#define B0 (1u << 5)
#define C0 (2u << 5)
#define D0 (3u << 5)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define MATRIX_ROWS 6
#define MATRIX_ROW_PINS { B0 + 4, B0 + 5, A0 + 8, A0 + 9, D0 + 8, D0 + 9 }
#define MATRIX_COL_PINS { A0 + 1, A0 + 2, C0 + 3 }
#define ENCODER_A_PINS { A0 + 5 }
#define ENCODER_B_PINS { A0 + 6 }
#define CHARGE_CHRG_PIN (B0 + 16)
typedef uint16_t matrix_row_t;
matrix_row_t matrix_get_row(uint8_t row);
bool gpio_read_pin(pin_t p);
void gpio_set_pin_output_push_pull(pin_t p);
void gpio_write_pin_low(pin_t p);
void gpio_write_pin_high(pin_t p);
void gpio_set_pin_input_high(pin_t p);
uint32_t last_input_activity_elapsed(void);
uint32_t last_encoder_activity_time(void);
typedef struct { uint8_t r, g, b; } rgb_t;
typedef struct { uint8_t h, s, v; } hsv_t;
rgb_t hsv_to_rgb(hsv_t hsv);
void rgb_matrix_reinit_effect(void);
