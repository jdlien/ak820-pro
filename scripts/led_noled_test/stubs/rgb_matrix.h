/* Host stub: just what drivers/led/sn32f2xx.c touches. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "matrix.h"

typedef uint32_t pin_t;
#define PAL_IOPORTS_WIDTH 32
#define PIN(port, pad) ((pin_t)(((port) << 5) | (pad)))
#define PAL_PORT(p) ((p) >> 5)
#define PAL_PAD(p) ((p) & 31)
#define A4 PIN(0,4)
#define A5 PIN(0,5)
#define A6 PIN(0,6)
#define A7 PIN(0,7)
#define A8 PIN(0,8)
#define A9 PIN(0,9)
#define A11 PIN(0,11)
#define A0 PIN(0,0)
#define A15 PIN(0,15)
#define B0 PIN(1,0)
#define B4 PIN(1,4)
#define B5 PIN(1,5)
#define C0 PIN(2,0)
#define C1 PIN(2,1)
#define C2 PIN(2,2)
#define C3 PIN(2,3)
#define C4 PIN(2,4)
#define C5 PIN(2,5)
#define C6 PIN(2,6)
#define C7 PIN(2,7)
#define C8 PIN(2,8)
#define C9 PIN(2,9)
#define C10 PIN(2,10)
#define C11 PIN(2,11)
#define C12 PIN(2,12)
#define C13 PIN(2,13)
#define C14 PIN(2,14)
#define C15 PIN(2,15)
#define D0 PIN(3,0)
#define D8 PIN(3,8)
#define D9 PIN(3,9)
#define D10 PIN(3,10)
#define D11 PIN(3,11)
#define D12 PIN(3,12)
#define D13 PIN(3,13)
#define D16 PIN(3,16)
#define D17 PIN(3,17)
#define D18 PIN(3,18)

void gpio_set_pin_output_push_pull(pin_t p);
void gpio_write_pin_low(pin_t p);
void gpio_write_pin_high(pin_t p);
void gpio_set_pin_input(pin_t p);
void gpio_set_pin_input_high(pin_t p);
void gpio_set_pin_input_low(pin_t p);

typedef struct PWMDriver PWMDriver;
typedef void (*pwmcallback_t)(PWMDriver *pwmp);
#define PWM_OUTPUT_DISABLED 0
#define PWM_OUTPUT_ACTIVE_HIGH 1
#define PWM_OUTPUT_ACTIVE_LOW 2
#define PWM_CHANNELS 12
typedef struct { uint32_t mode; pwmcallback_t callback; uint32_t pfpamsk; } PWMChannelConfig;
typedef struct { uint32_t frequency; uint32_t period; pwmcallback_t callback; PWMChannelConfig channels[PWM_CHANNELS]; uint32_t hw; } PWMConfig;
struct PWMDriver { const PWMConfig *config; uint32_t mr[16]; uint8_t en[16]; };
extern PWMDriver PWMD0, PWMD1, PWMD2;
void pwmStart(PWMDriver *d, const PWMConfig *c);
void pwmEnableChannel(PWMDriver *d, uint32_t ch, uint32_t w);
void pwmDisableChannel(PWMDriver *d, uint32_t ch);
void pwmDisableChannelI(PWMDriver *d, uint32_t ch);
void pwmEnablePeriodicNotification(PWMDriver *d);
void pwmDisablePeriodicNotification(PWMDriver *d);
void pwmEnablePeriodicNotificationI(PWMDriver *d);
void pwmDisablePeriodicNotificationI(PWMDriver *d);
#define pwm_lld_change_counter(d, v) ((void)(d), (void)(v))
#define SN32_CT_PWM_GET(d, f) (0u)
#define SN32_CT_PWM_SET(d, f, v) ((void)(v))
#define NVIC_ClearPendingIRQ(n) ((void)(n))
#define CT16B1_IRQn 0
struct pfpa { uint32_t CT16B0, CT16B1, CT16B2; };
extern struct pfpa pfpa_regs;
#define SN_PFPA (&pfpa_regs)

#define chSysLock() do {} while (0)
#define chSysUnlock() do {} while (0)
#define chSysLockFromISR() do {} while (0)
#define chSysUnlockFromISR() do {} while (0)
#define TIME_US2I(us) (6)

typedef enum { FLASH_UNINIT, FLASH_STOP, FLASH_READY, FLASH_READ, FLASH_PGM, FLASH_ERASE } flash_state_t;
typedef struct { flash_state_t state; } EFlashDriver;
extern EFlashDriver EFLD1;
uint32_t timer_read32(void);

typedef struct { uint8_t r, g, b; } RGB;
#define NO_LED 255
typedef struct { uint8_t matrix_co[MATRIX_ROWS][MATRIX_COLS]; } led_config_t;
extern led_config_t g_led_config;
