/* Link stubs for the board modules sleep.c and power.c call. Each returns the
 * steady state of an awake board with no recovery and no sleep wanted:
 * nothing here calls the timer, so every timer read counted is the real
 * firmware's own. */
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include "hal.h"
#include "quantum.h"

host_usb_t host_usb; host_uart_t host_uart2; host_spi_t host_spi0, host_spi1;
host_wdt_t host_wdt; host_rtc_t host_rtc; host_nvic_t host_nvic; host_adc_t host_adc;
host_systick_t host_systick; host_scb_t host_scb; host_ct16_t host_ct16b5;
host_gpio_t host_gpio0, host_gpio1, host_gpio2; host_sys0_t host_sys0; host_flash_t host_flash;
host_pmu_t host_pmu;
SerialDriver SD2; EFlashDriver EFLD1; USBDriver USB_DRIVER_OBJ;
uint32_t host_ticks; unsigned host_n_lock, host_n_i2ms; uint64_t host_div_iters;

bool host_on_battery;
unsigned host_n_blockers_calls;

void NVIC_SystemReset(void) { abort(); }
bool oqIsEmptyI(host_queue_t *q) { (void)q; return true; }
bool iqIsEmptyI(host_queue_t *q) { (void)q; return true; }
void iqResetI(host_queue_t *q) { (void)q; }
void usb_lld_connect_bus(USBDriver *u) { (void)u; }
void usb_lld_disconnect_bus(USBDriver *u) { (void)u; }
matrix_row_t matrix_get_row(uint8_t row) { (void)row; return 0; }
bool gpio_read_pin(pin_t p) { (void)p; return true; }
void gpio_set_pin_output_push_pull(pin_t p) { (void)p; }
void gpio_write_pin_low(pin_t p) { (void)p; }
void gpio_write_pin_high(pin_t p) { (void)p; }
void gpio_set_pin_input_high(pin_t p) { (void)p; }
uint32_t last_encoder_activity_time(void) { return 0; }
void last_matrix_activity_trigger(void) {}
void last_encoder_activity_trigger(void) {}
uint8_t encoder_quadrature_state(uint8_t i) { (void)i; return 3; }
rgb_t hsv_to_rgb(hsv_t h) { rgb_t r = {h.v, h.v, h.v}; return r; }
void rgb_matrix_reinit_effect(void) {}

uint16_t battery_avg_minutes(void) { return 0; }
uint16_t battery_level_permille(void) { return 800; }
bool battery_on_battery(void) { return host_on_battery; }
uint16_t battery_session_count(void) { return 0; }
void battery_sleep_account(uint32_t ms) { (void)ms; }
void battery_sleep_enter(void) {}
void battery_sleep_wake(void) {}
uint16_t battery_supply_samples(void) { return 0; }
uint16_t battery_time_left_min(void) { return 0xFFFF; }
void ch582_battery_poll_release(void) {}
uint16_t ch582_battery_reports(void) { return 0; }
bool ch582_is_pairing(void) { return false; }
void ch582_rx_resync(void) {}
void ch582_sleep_wake(void) {}
bool ch582_tx_idle(void) { return true; }
uint8_t display_backlight_effective(void) { return 80; }
bool display_band_busy(void) { return false; }
bool display_bus_idle(void) { host_n_blockers_calls++; return true; }
bool display_menu_sleep_blocked(void) { return false; }
bool display_message_recent(uint32_t ms) { (void)ms; return false; }
bool display_panel_lit_for_owner(void) { return false; }
void display_set_backlight_cap(uint8_t c) { (void)c; }
void display_set_param_status(const char *s) { (void)s; }
void display_sleep_wake(void) {}
void display_wake_corrected(void) {}
void display_wake_release(void) {}
bool display_wake_repainted(void) { return true; }
uint16_t health_key_presses(void) { return 0; }
bool kb_eeconfig_get_power_mode(uint8_t *m) { (void)m; return false; }   /* fresh flash: POWER_MODE_DEFAULT */
void kb_eeconfig_set_power_mode(uint8_t m) { (void)m; }
bool kb_eeconfig_write_pending(void) { return false; }
void pwm_tick_startI(void) {}
void pwm_tick_stopI(void) {}
void rtc_account_sleepI(uint32_t s) { (void)s; }
void rtc_pass_mark(void) {}
bool rtc_pass_used_bus(void) { return false; }
bool rtc_sleep_ok(void) { return true; }
bool rtc_sleep_prepare(void) { return false; }
void rtc_wake_abandon(void) {}
uint8_t rtc_wake_acq_result(void) { return 2; }
int16_t rtc_wake_acq_step_ms(void) { return 0; }
void rtc_wake_allow(void) {}
void rtc_wake_beginI(uint32_t s) { (void)s; }
bool rtc_wake_busy(void) { return false; }
void rtc_wake_gauge_taken(void) {}
bool rtc_wake_slept(uint32_t *s, bool *p) { (void)s; (void)p; return false; }
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void watchdog_record_leave(uint32_t *prev) { (void)prev; }
void watchdog_record_stop(uint8_t site, uint8_t exception, uint32_t pc) { (void)site; (void)exception; (void)pc; }
bool watchdog_running(void) { return true; }
void sn32f2xx_sleep_enterI(void) {}
void sn32f2xx_sleep_exitI(void) {}
bool sn32f2xx_led_committed_dark(void) { return false; }
void sn32f2xx_set_power_scale(uint8_t s) { (void)s; }
