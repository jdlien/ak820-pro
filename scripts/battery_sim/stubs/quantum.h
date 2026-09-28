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
#define RGB_MATRIX_LED_COUNT 82
