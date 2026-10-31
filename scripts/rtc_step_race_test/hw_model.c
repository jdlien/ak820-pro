/* verify-020: a cycle-level model of the SN32F299's RTC prescaler and of
 * ChibiOS's ARMv6-M lock (cpsid/cpsie), driving the REAL rtc.c, the REAL SN32
 * RTC LLD (hal_rtc_lld.c) and the REAL ChibiOS hal_rtc.c.
 *
 * The RTC (docs/sn32f299.md, section 9, from the manual p. 154-157):
 *  - SECCNT counts 0..SECCNTV on the ILRC, then wraps to 0 and raises SECIF
 *    (RIS bit 0) at the match: SECCNTV + 1 counts per second;
 *  - writing SECCNTV resets SECCNT (documented, p. 157);
 *  - writing IC clears the RIS bits written;
 *  - SECIF stays latched until IC clears it. The manual does not say that a
 *    SECCNTV write clears it, and the model assumes it does not.
 * The interrupt line is RIS & IE: with PRIMASK set (chSysLock) the handler
 * waits, and it runs at the unlock if the flag is still latched; on return it
 * runs again while the line is still asserted (tail-chaining).
 *
 * Register writes are noticed at the points the firmware's code always passes
 * right after them: rtc_lld_set_period() writes SECCNTV and then calls
 * osalSysRestoreStatusX(); the handler writes IC and returns to the model. A
 * SECCNTV write is detected through a sentinel (no code under test reads
 * SECCNTV back: it reads RTCD1.period). */
#include "hal.h"
#include "graphics/display.h"
#include "graphics/lcd_bus.h"
#include "kb_eeconfig.h"
#include "rtc_persist.h"
#include "sleep.h"
#include "watchdog_record.h"
#include "drivers/led/sn32f2xx.h"
#include "hw_model.h"

SN_RTC_Type fake_rtc;
SN_USB_Type fake_usb;
NVIC_Type   fake_nvic;
I2CDriver   I2CD1;
USBDriver   USBD1;
volatile uint8_t loop_stall_mark;

#define SECCNTV_SENTINEL 0xFFFFFFFFu

hw_t hw;

static void hw_sync(void)
{
    if (fake_rtc.IC) {                       /* IC: clear the written flags */
        fake_rtc.RIS &= ~fake_rtc.IC;
        fake_rtc.IC = 0;
    }
    if (fake_rtc.SECCNTV != SECCNTV_SENTINEL) {   /* a SECCNTV write */
        uint32_t v = fake_rtc.SECCNTV & 0xFFFFFu;
        hw.reload = v ? v : 0x8000u;
        fake_rtc.SECCNT = 0;                 /* the write resets the counter */
        hw.reload_writes++;
        hw_log("SECCNTV <- %lu (SECCNT reset) at cycle %llu, locked=%d",
               (unsigned long)hw.reload, (unsigned long long)hw.now, hw.locked);
        fake_rtc.SECCNTV = SECCNTV_SENTINEL;
    }
}

static void hw_dispatch(void)
{
    while (!hw.locked && !hw.in_isr && (fake_rtc.RIS & fake_rtc.IE & 1u)) {
        hw.in_isr = true;
        hw.isr_runs++;
        hw_log("RTC IRQ taken at cycle %llu (SECCNT %lu)", (unsigned long long)hw.now,
               (unsigned long)fake_rtc.SECCNT);
        fake_rtc_irq_handler();
        hw_sync();
        hw.in_isr = false;
    }
}

void hw_lock(void)
{
    hw.locked = true;
    hw.lock_count++;
    if (hw.lock_hook) {
        void (*h)(void) = hw.lock_hook;
        hw.lock_hook = NULL;                 /* one shot */
        h();
    }
}

void hw_unlock(void)
{
    hw_sync();
    hw.locked = false;
    hw_dispatch();
}

syssts_t hw_get_status_and_lock(void)
{
    syssts_t s = hw.locked;
    hw.locked = true;
    return s;
}

void hw_restore_status(syssts_t s)
{
    hw_sync();
    hw.locked = s != 0;
    hw_dispatch();
}

/* One ILRC cycle. */
static void hw_cycle(void)
{
    hw.now++;
    if (fake_rtc.CTRL & 1u) {
        if (fake_rtc.SECCNT >= hw.reload) {
            fake_rtc.SECCNT = 0;
            fake_rtc.RIS |= 1u;              /* SECIF at the match */
            hw.matches++;
            hw_log("match at cycle %llu, locked=%d", (unsigned long long)hw.now, hw.locked);
        } else {
            fake_rtc.SECCNT++;
        }
    }
    hw_dispatch();
}

void hw_advance(uint64_t cycles)
{
    while (cycles--) hw_cycle();
}

void hw_reset(void)
{
    memset(&hw, 0, sizeof hw);
    memset(&fake_rtc, 0, sizeof fake_rtc);
    fake_rtc.SECCNTV = SECCNTV_SENTINEL;
    hw.reload = 0x8000u;
}

void hw_log(const char *fmt, ...)
{
    if (!hw.verbose) return;
    va_list ap;
    va_start(ap, fmt);
    fputs("    hw: ", stdout);
    vprintf(fmt, ap);
    fputc('\n', stdout);
    va_end(ap);
}

/* ---- I2C: a PCF8563 that answers the 7-byte calendar read with hw.pcf ---- */
static uint8_t dec2bcd_(uint8_t v) { return (uint8_t)(((v / 10) << 4) | (v % 10)); }

void i2cStart(I2CDriver *d, const I2CConfig *c) { (void)d; (void)c; }
void i2cStop(I2CDriver *d) { (void)d; }
msg_t i2cMasterTransmitTimeout(I2CDriver *d, uint8_t addr, const uint8_t *tx, size_t ntx,
                               uint8_t *rx, size_t nrx, sysinterval_t t)
{
    (void)d; (void)addr; (void)t;
    hw.i2c_xfers++;
    if (ntx == 1 && tx[0] == 0x02 && nrx == 7) {
        rx[0] = dec2bcd_(hw.pcf_sec);
        rx[1] = dec2bcd_(hw.pcf_min);
        rx[2] = dec2bcd_(hw.pcf_hour);
        rx[3] = dec2bcd_(hw.pcf_day);
        rx[4] = hw.pcf_wday;
        rx[5] = dec2bcd_(hw.pcf_mon);
        rx[6] = dec2bcd_(hw.pcf_year);
        return MSG_OK;
    }
    if (nrx) memset(rx, 0, nrx);
    return MSG_OK;
}

/* ---- the rest of the board, inert ---- */
bool          display_bus_idle(void) { return true; }
void          display_defer_pass(void) {}
bool          display_splash_done(void) { return true; }
uint16_t      kb_eeconfig_get_rtc_period(void) { return 0; }   /* nothing stored: RTC_PERIOD_INITIAL */
uint32_t      last_input_activity_elapsed(void) { return 0; }
bool          lcd_blit_busy(void) { return false; }
bool          lcd_blit_wait(void) { return true; }
void          rtc_persist_propose(uint16_t period, uint8_t path) { (void)period; (void)path; }
void          rtc_persist_task(void) {}
sysinterval_t sleep_pass_ticks(void) { return 0; }
bool          sleep_recovering(void) { return false; }
bool          sn32f2xx_led_committed_dark(void) { return false; }
usbstate_t    usbGetDriverStateI(USBDriver *u) { (void)u; return USB_ACTIVE; }
systime_t     chVTGetSystemTimeX(void) { return (systime_t)hw.now; }
uint32_t      watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void          watchdog_record_leave(uint32_t *previous) { (void)previous; }
