/* The rest of the board, as seen by sleep.c and bt_ui.c: every other deep-
 * sleep precondition is held in its "idle, ready to sleep" state, so the only
 * blocker the real blockers() can report is the one under test. Compiled
 * against stubs_sys/ and the board's own headers. */
#include <stdio.h>
#include "hal.h"
#include "quantum.h"
#include "connection.h"
#include "drivers/led/sn32f2xx.h"

uint32_t now_ms = 0;

/* registers: plain host memory */
usb_regs_t host_usb; sys0_regs_t host_sys0;
gpio_regs_t host_gpio0, host_gpio1, host_gpio2;
uart_regs_t host_uart2 = {.LS = (1u << 6)};   /* UART2 transmitter empty (TEMT) */
flash_regs_t host_flash; adc_regs_t host_adc;
wdt_regs_t host_wdt = {.CFG = 1u};            /* WDTEN */
spi_regs_t host_spi0, host_spi1; rtc_regs_t host_rtc; pmu_regs_t host_pmu;
nvic_regs_t host_nvic; scb_regs_t host_scb; systick_regs_t host_systick; st_tim_t host_st_tim;
EFlashDriver EFLD1 = {FLASH_STOP};
USBDriver USBD1;
SerialDriver SD2;

/* time */
uint16_t timer_read(void) { return (uint16_t)now_ms; }
uint32_t timer_read32(void) { return now_ms; }
uint16_t timer_elapsed(uint16_t t) { return (uint16_t)((uint16_t)now_ms - t); }
uint32_t timer_elapsed32(uint32_t t) { return now_ms - t; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)(now_ms * 187u); }
void chSysLock(void) {}
void chSysUnlock(void) {}
void chThdSleepMilliseconds(uint32_t ms) { (void)ms; }
bool oqIsEmptyI(output_queue_t *q) { (void)q; return true; }
void iqResetI(input_queue_t *q) { (void)q; }
void NVIC_SystemReset(void) { fprintf(stderr, "NVIC_SystemReset called\n"); __builtin_trap(); }
void usb_lld_connect_bus(USBDriver *u) { (void)u; }
void usb_lld_disconnect_bus(USBDriver *u) { (void)u; }

/* input: the key the test holds, and the time of the last input */
int      key_down       = 0;
uint32_t last_input_ms  = 0;
matrix_row_t matrix_get_row(uint8_t row) { return (key_down && row == 1) ? 1u : 0u; }
uint32_t last_input_activity_elapsed(void) { return now_ms - last_input_ms; }
uint32_t last_encoder_activity_time(void) { return 0; }
void last_matrix_activity_trigger(void) { last_input_ms = now_ms; }
void last_encoder_activity_trigger(void) { last_input_ms = now_ms; }
void clear_keyboard(void) {}
void connection_set_host_noeeprom(connection_host_t host) { (void)host; }

/* pins: CHRG high (not charging); the knob's pins and the decoder agree */
bool gpio_read_pin(pin_t pin) { (void)pin; return true; }
void gpio_set_pin_input_high(pin_t pin) { (void)pin; }
void gpio_set_pin_output_push_pull(pin_t pin) { (void)pin; }
void gpio_write_pin_high(pin_t pin) { (void)pin; }
void gpio_write_pin_low(pin_t pin) { (void)pin; }
uint8_t encoder_quadrature_state(uint8_t index) { (void)index; return 3u; }

/* the power ladder: on battery, Balanced (power.c:64: asleep at 20 min idle).
 * power_sleep_wanted() is power.c's own rule for that mode, restated. */
#define BALANCED_SLEEP_MS 1200000u
bool power_sleep_wanted(void) { return last_input_activity_elapsed() >= BALANCED_SLEEP_MS; }
bool power_rgb_dark(void) { return true; }
void power_task(void) {}
bool sn32f2xx_led_committed_dark(void) { return true; }
void sn32f2xx_sleep_enterI(void) {}
void sn32f2xx_sleep_exitI(void) {}
void pwm_tick_startI(void) {}
void pwm_tick_stopI(void) {}

/* the display: dark and idle */
bool display_bus_idle(void) { return true; }
uint8_t display_backlight_effective(void) { return 0; }
bool display_menu_sleep_blocked(void) { return false; }
void display_sleep_wake(void) {}
void display_set_pair_hint(int16_t pct) { (void)pct; }
void display_draw_bluetooth_logo(void) {}
void display_draw_2_4_g_logo(void) {}
void display_draw_usb_logo(void) {}

/* flash/eeconfig: no deferred write owed */
bool kb_eeconfig_write_pending(void) { return false; }
static uint8_t bt_prof = 0x31;
void kb_eeconfig_set_bt_profile(uint8_t p) { bt_prof = p; }
uint8_t kb_eeconfig_get_bt_profile(void) { return bt_prof; }

/* watchdog running */
bool watchdog_running(void) { return true; }

/* RTC: idle. rtc_sleep_prepare() is the probe: sleep.c calls it only once
 * blockers() == 0 (sleep.c:961-963). It returns false so the sleep itself is
 * never entered on the host; each call is a pass where the board would sleep. */
uint32_t sleep_eligible_passes = 0;
uint32_t first_eligible_ms     = 0;
bool rtc_sleep_ok(void) { return true; }
bool rtc_sleep_prepare(void) {
    if (sleep_eligible_passes++ == 0) first_eligible_ms = now_ms;
    return false;
}
void rtc_pass_mark(void) {}
int16_t rtc_wake_acq_step_ms(void) { return 0; }

/* battery */
void battery_sleep_enter(void) {}

/* Reached only from the sleep itself and the wake's recovery, which never run
 * here (rtc_sleep_prepare() returns false; rc_active stays false). They trap
 * if that assumption is ever wrong. */
#define NOT_HERE() do { fprintf(stderr, "unexpected: %s\n", __func__); __builtin_trap(); } while (0)
void battery_sleep_account(uint32_t slept_ms) { (void)slept_ms; NOT_HERE(); }
void battery_sleep_wake(void) { NOT_HERE(); }
uint16_t battery_supply_samples(void) { NOT_HERE(); }
void display_wake_corrected(void) { NOT_HERE(); }
void display_wake_release(void) { NOT_HERE(); }
bool display_wake_repainted(void) { NOT_HERE(); }
uint16_t health_key_presses(void) { NOT_HERE(); }
void power_wake_notice(void) { NOT_HERE(); }
void rtc_account_sleepI(uint32_t seconds) { (void)seconds; NOT_HERE(); }
bool rtc_pass_used_bus(void) { NOT_HERE(); }
void rtc_wake_abandon(void) { NOT_HERE(); }
uint8_t rtc_wake_acq_result(void) { NOT_HERE(); }
void rtc_wake_allow(void) { NOT_HERE(); }
void rtc_wake_beginI(uint32_t counted_s) { (void)counted_s; NOT_HERE(); }
bool rtc_wake_busy(void) { NOT_HERE(); }
void rtc_wake_gauge_taken(void) { NOT_HERE(); }
bool rtc_wake_slept(uint32_t *slept_s, bool *from_pcf) { (void)slept_s; (void)from_pcf; NOT_HERE(); }
uint32_t watchdog_record_enter(uint8_t site) { (void)site; NOT_HERE(); }
void watchdog_record_leave(uint32_t *previous) { (void)previous; NOT_HERE(); }
