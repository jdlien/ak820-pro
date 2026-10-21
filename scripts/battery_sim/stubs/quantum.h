/* Host stand-in for QMK's quantum.h: just what battery.c and power.c touch.
 * The simulated world behind these lives in sim.c. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* The ADC. Every access through SN_ADC sets EOC first, so battery.c's
 * conversion loop sees a finished conversion on its first read, and ADB holds
 * whatever code sim.c put there. */
struct fake_adc { uint32_t ADM; uint32_t ADB; };
extern struct fake_adc fake_adc;
static inline struct fake_adc *fake_adc_ptr(void) {
    fake_adc.ADM |= (1u << 6);
    return &fake_adc;
}
#define SN_ADC (fake_adc_ptr())
static inline void sys1SelectADCPRE(int x) { (void)x; }
static inline void sys1EnableADC(void) {}
static inline void sys1ResetADC(void) {}
static inline void wait_us(int x) { (void)x; }
static inline void chSysLock(void) {}
static inline void chSysUnlock(void) {}

uint32_t timer_read32(void);
uint32_t timer_elapsed32(uint32_t last);
uint32_t last_input_activity_elapsed(void);

#define B16 16
#define B17 17
#define CHARGE_CHRG_PIN  B16
#define CHARGE_STDBY_PIN B17
bool gpio_read_pin(int pin);

bool rgb_matrix_is_enabled(void);
/* QMK's colour types (quantum/color.h), for power.c's dim hook. The colour
 * build (SIM_REAL_COLOUR) links QMK's own color.c, so it takes QMK's own
 * declarations too: one type on both sides of the call (run.sh puts
 * quantum/ last on its include path). */
#ifdef SIM_REAL_COLOUR
#include "color.h"
#else
typedef struct { uint8_t r, g, b; } rgb_t;
typedef struct { uint8_t h, s, v; } hsv_t;
rgb_t hsv_to_rgb(hsv_t hsv);
#endif
uint8_t rgb_matrix_get_mode(void);
void    rgb_matrix_mode_noeeprom(uint8_t mode);
void    rgb_matrix_reinit_effect(void);
#define RGB_MATRIX_LED_COUNT 81   /* the board's, keyboard.json (82 until 10-21) */
