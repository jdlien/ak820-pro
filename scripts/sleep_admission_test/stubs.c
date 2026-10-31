/* Definitions behind stubs/fw_hal_stub.h, and the board functions sleep.c and
 * ch582f_ajazz.c call that are not under test. Verify-032. */
#include "stubs/fw_hal_stub.h"
#include <assert.h>

/* ---- time: one counter in ms, the system time at 187.5 kHz ---- */
uint32_t g_ms = 1000;
uint16_t timer_read(void) { return (uint16_t)g_ms; }
uint32_t timer_read32(void) { return g_ms; }
uint16_t timer_elapsed(uint16_t last) { return (uint16_t)((uint16_t)g_ms - last); }
uint32_t timer_elapsed32(uint32_t last) { return g_ms - last; }
void     wait_ms(uint32_t ms) { g_ms += ms; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)((uint64_t)g_ms * 1875u / 10u); }
uint32_t  st_lld_get_counter(void) { return chVTGetSystemTimeX() & 0xFFFFu; }

/* ---- the lock: PRIMASK as a depth; the UART ISR may only run outside it ---- */
int  g_lock_depth = 0;
void chSysLock(void) { assert(g_lock_depth == 0); g_lock_depth++; }
void chSysUnlock(void) { assert(g_lock_depth == 1); g_lock_depth--; }
syssts_t chSysGetStatusAndLockX(void) { syssts_t s = (syssts_t)g_lock_depth; if (!g_lock_depth) g_lock_depth = 1; return s; }
void     chSysRestoreStatusX(syssts_t s) { if (!s) g_lock_depth = 0; }

/* ---- the queues: ChibiOS hal_queues.c's iqPutI / iqGetI / iqResetI ---- */
SerialDriver SD2;
size_t g_iq_reset_discarded = 0;   /* bytes iqResetI threw away, last call */
unsigned g_iq_resets = 0;

static void q_init(io_queue_t *q, uint8_t *b, size_t n) {
    q->q_buffer = q->q_rdptr = q->q_wrptr = b;
    q->q_top = b + n;
    q->q_counter = 0;
}
void iqResetI(input_queue_t *iqp) {
    assert(g_lock_depth == 1);   /* I-class */
    g_iq_reset_discarded = iqp->q_counter;
    g_iq_resets++;
    iqp->q_rdptr = iqp->q_buffer;
    iqp->q_wrptr = iqp->q_buffer;
    iqp->q_counter = 0;
}
msg_t iqPutI(input_queue_t *iqp, uint8_t b) {
    if (iqIsFullI(iqp)) return MSG_TIMEOUT;
    iqp->q_counter++;
    *iqp->q_wrptr++ = b;
    if (iqp->q_wrptr >= iqp->q_top) iqp->q_wrptr = iqp->q_buffer;
    return MSG_OK;
}
msg_t iqGetI(input_queue_t *iqp) {
    if (iqIsEmptyI(iqp)) return MSG_TIMEOUT;
    iqp->q_counter--;
    uint8_t b = *iqp->q_rdptr++;
    if (iqp->q_rdptr >= iqp->q_top) iqp->q_rdptr = iqp->q_buffer;
    return b;
}
void sdStart(SerialDriver *sdp, const SerialConfig *cfg) {
    (void)cfg;
    q_init(&sdp->iqueue, sdp->ib, sizeof sdp->ib);
    q_init(&sdp->oqueue, sdp->ob, sizeof sdp->ob);
}
/* Non-blocking read (TIME_IMMEDIATE), as the drain calls it. */
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t) {
    assert(t == TIME_IMMEDIATE);
    assert(g_lock_depth == 0);
    size_t k = 0;
    while (k < n) {
        chSysLock();
        msg_t m = iqGetI(&sdp->iqueue);
        chSysUnlock();
        if (m < MSG_OK) break;
        b[k++] = (uint8_t)m;
    }
    return k;
}
/* The board's transmissions: logged; the line is treated as drained at once
 * (the output queue stays empty and TEMT set), which only helps the sleep's
 * TX admission pass. The module model ACKs every command frame. */
uint8_t  g_tx_log[4096];
size_t   g_tx_n = 0;
unsigned g_tx_frames = 0, g_tx_acks_sent = 0;
unsigned g_pending_module_acks = 0;
size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n) {
    (void)sdp;
    for (size_t i = 0; i < n && g_tx_n < sizeof g_tx_log; i++) g_tx_log[g_tx_n++] = b[i];
    if (n == 3 && b[0] == 0x61 && b[1] == 0x0D && b[2] == 0x0A) g_tx_acks_sent++;
    else { g_tx_frames++; g_pending_module_acks++; }
    return n;
}
void chEvtRegisterMaskWithFlags(event_source_t *s, event_listener_t *l, eventmask_t m, eventflags_t f) {
    (void)s; (void)m; (void)f; l->flags = 0;
}
eventflags_t chEvtGetAndClearFlags(event_listener_t *l) { eventflags_t f = l->flags; l->flags = 0; return f; }

/* ---- registers ---- */
sn_usb_t g_usb; sn_uart_t g_uart2; sn_adc_t g_adc;
sn_gpio_t g_gpio0, g_gpio1, g_gpio2; nvic_t g_nvic; scb_t g_scb;
systick_t g_systick; sn_ct16_t g_ct16b5; sn_sys0_t g_sys0;
sn_flash_t g_flash; sn_pmu_t g_pmu; sn_rtc_t g_rtc; sn_wdt_t g_wdt;
sn_spi_t g_spi0, g_spi1;
EFlashDriver EFLD1 = {FLASH_STOP};
USBDriver USBD1;
void usb_lld_connect_bus(USBDriver *u) { (void)u; }
void usb_lld_disconnect_bus(USBDriver *u) { (void)u; }
void NVIC_SystemReset(void) { fprintf(stderr, "NVIC_SystemReset reached\n"); abort(); }

/* Pins: every input reads high (pull-ups: no key, knob at rest 11, CHRG off). */
bool gpio_read_pin(pin_t p) { (void)p; return true; }
void gpio_write_pin_low(pin_t p) { (void)p; }
void gpio_write_pin_high(pin_t p) { (void)p; }
void gpio_set_pin_output_push_pull(pin_t p) { (void)p; }
void gpio_set_pin_input_high(pin_t p) { (void)p; }
uint8_t encoder_quadrature_state(uint8_t i) { (void)i; return 3; }

/* ---- the board functions not under test ---- */
typedef uint16_t matrix_row_t;
matrix_row_t matrix_get_row(uint8_t r) { (void)r; return 0; }
bool g_sleep_wanted = false;
bool power_sleep_wanted(void) { return g_sleep_wanted; }
bool power_rgb_dark(void) { return true; }
void power_task(void) {}
void power_wake_notice(void) {}
bool display_bus_idle(void) { return true; }
uint8_t display_backlight_effective(void) { return 0; }
bool display_menu_sleep_blocked(void) { return false; }
void display_sleep_wake(void) {}
void display_wake_corrected(void) {}
void display_wake_release(void) {}
bool display_wake_repainted(void) { return true; }
bool kb_eeconfig_write_pending(void) { return false; }
bool rtc_sleep_ok(void) { return true; }
bool watchdog_running(void) { return true; }
bool sn32f2xx_led_committed_dark(void) { return true; }
void sn32f2xx_sleep_enterI(void) {}
void sn32f2xx_sleep_exitI(void) {}
void pwm_tick_startI(void) {}
void pwm_tick_stopI(void) {}
void battery_5c_report(uint8_t d) { (void)d; }
void battery_sleep_account(uint32_t ms) { (void)ms; }
void battery_sleep_enter(void) {}
void battery_sleep_wake(void) {}
uint16_t battery_supply_samples(void) { return 0; }
uint16_t health_key_presses(void) { return 0; }
void health_note_rx_malformed(void) {}
uint32_t last_encoder_activity_time(void) { return 0; }
void last_encoder_activity_trigger(void) {}
void last_matrix_activity_trigger(void) {}
bool loop_acct_on = false;
uint32_t loop_acct_run[32];
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void watchdog_record_leave(uint32_t *prev) { (void)prev; }
void watchdog_record_stop(uint8_t site, uint8_t exception, uint32_t pc) { (void)site; (void)exception; (void)pc; }
void rtc_account_sleepI(uint32_t s) { (void)s; }
void rtc_pass_mark(void) {}
bool rtc_pass_used_bus(void) { return false; }
void rtc_wake_abandon(void) {}
uint8_t rtc_wake_acq_result(void) { return 0; }
uint16_t rtc_wake_acq_step_ms(void) { return 0; }
void rtc_wake_allow(void) {}
void rtc_wake_beginI(uint32_t s) { (void)s; }
bool rtc_wake_busy(void) { return false; }
void rtc_wake_gauge_taken(void) {}
bool rtc_wake_slept(uint32_t *s, bool *pcf) { *s = 0; *pcf = false; return true; }

/* rtc_sleep_prepare(): its PCF "before" read takes ~2.6 ms on the software I2C
 * (CLAUDE.md, "the PCF's 2.6 ms transaction"), interrupts enabled. The test
 * hooks what the UART ISR does in that time. */
void (*g_during_pcf_read)(void) = NULL;
bool rtc_sleep_prepare(void) {
    assert(g_lock_depth == 0);
    if (g_during_pcf_read) g_during_pcf_read();
    g_ms += 3;
    return true;
}
