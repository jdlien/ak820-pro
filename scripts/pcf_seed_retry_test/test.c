/* A failed first PCF read is retried (plans/AUDIT-2026-10-31.md, F-006; first
 * written as the audit's verify-019). Before the fix nothing but a host set
 * rtc_valid after rtc_init's one seed, so the clock stayed "unset" (00:00 on
 * the dashboard) until a host sync; rtc_task() now retries the seed every
 * 60 counted seconds.
 *
 * Links the REAL keyboards/a_jazz/ak820pro/rtc/rtc.c (compiled by path, not
 * edited) against host stubs: a software SN32 RTC (the LLD's time_t plus the
 * second interrupt calling rtc.c's registered callback), a PCF8563 register
 * model on the I2C call, and a main loop that runs rtc_fast_task() every pass,
 * rtc_task() at 10 Hz and rtc_pass_mark() at each pass's end, as ak820pro.c
 * and sleep.c do.
 *
 * Scenarios (argv[1]):
 *   control : the boot read succeeds          -> clock valid, acquisition DONE
 *   first   : only the FIRST PCF transaction fails (the seed in rtc_init),
 *             the PCF is healthy afterwards, on battery, no host -> valid by
 *             120 s, acquisition DONE
 *   bug     : the same, asserting the behaviour before the fix (fails now)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "hal.h"
#include "rtc.h"
void rtc_status_fill_page4(uint8_t *out);   /* rtc.c, not in rtc.h */

/* ------------------------------------------------------------------ */
/* Globals rtc.c links against                                         */
/* ------------------------------------------------------------------ */
RTCDriver   RTCD1;
I2CDriver   I2CD1;
USBDriver   USBD1;
SN_RTC_Type sim_rtc_regs;
SN_USB_Type sim_usb_regs;
NVIC_Type   sim_nvic = { { 1u << CT16B1_IRQn } };
int         sim_lock_depth;
volatile uint8_t loop_stall_mark;

static uint64_t   sim_ms;              /* simulated wall time since power-on, ms */
static usbstate_t sim_usb = USB_STOP;  /* on battery: no USB host */

/* ------------------------------------------------------------------ */
/* The SN32 RTC: ChibiOS conversions + the SN32 LLD's software time_t   */
/* ------------------------------------------------------------------ */
static const uint16_t accu_month_len[12] = { 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334 };

void rtcConvertDateTimeToStructTm(const RTCDateTime *timespec, struct tm *timp, uint32_t *tv_msec) {
    int sec, year;
    bool is_leap_year;
    memset(timp, 0, sizeof(*timp));
    timp->tm_year  = (int)timespec->year + (int)(RTC_BASE_YEAR - 1900U);
    timp->tm_mon   = (int)timespec->month - 1;
    timp->tm_mday  = (int)timespec->day;
    timp->tm_isdst = (int)timespec->dstflag;
    timp->tm_wday  = (int)timespec->dayofweek % 7;
    sec = (int)timespec->millisecond / 1000;
    timp->tm_hour = sec / 3600;
    sec %= 3600;
    timp->tm_min = sec / 60;
    timp->tm_sec = sec % 60;
    if (NULL != tv_msec) *tv_msec = (uint32_t)timespec->millisecond % 1000U;
    year = timp->tm_year + 1900;
    timp->tm_yday = timp->tm_mday - 1;
    if (timp->tm_mon >= 0 && timp->tm_mon < 12) timp->tm_yday += (int)accu_month_len[timp->tm_mon];
    is_leap_year = (((year % 4) == 0) && ((year % 100) != 0)) || ((year % 400) == 0);
    if (is_leap_year && (timp->tm_mon > 1)) timp->tm_yday++;
}

void rtcConvertStructTmToDateTime(const struct tm *timp, uint32_t tv_msec, RTCDateTime *timespec) {
    timespec->year      = (uint32_t)timp->tm_year - (RTC_BASE_YEAR - 1900U);
    timespec->month     = (uint32_t)timp->tm_mon + 1U;
    timespec->day       = (uint32_t)timp->tm_mday;
    timespec->dayofweek = (((uint32_t)timp->tm_wday + 6) % 7) + 1U;
    timespec->dstflag   = (-1 == timp->tm_isdst) ? 0U : (uint32_t)timp->tm_isdst;
    timespec->millisecond = tv_msec + (uint32_t)(((timp->tm_hour * 3600) + (timp->tm_min * 60) + timp->tm_sec) * 1000);
}

static volatile time_t lld_time = 0;   /* rtc_lld_init: rtc_time = (time_t)0 */

void rtcSetTime(RTCDriver *rtcp, const RTCDateTime *ts) {
    (void)rtcp;
    struct tm tim;
    rtcConvertDateTimeToStructTm(ts, &tim, NULL);
    lld_time = mktime(&tim);
}
void rtcGetTime(RTCDriver *rtcp, RTCDateTime *ts) {
    (void)rtcp;
    struct tm tim;
    time_t t = lld_time;
    localtime_r(&t, &tim);
    rtcConvertStructTmToDateTime(&tim, 0, ts);
}
void rtcSetCallback(RTCDriver *rtcp, rtccb_t cb) { rtcp->callback = cb; }
void rtc_lld_add_secondsI(RTCDriver *rtcp, uint32_t s) { (void)rtcp; lld_time += (time_t)s; }

/* The ILRC: SECCNT counts cycles; a match (SECCNT > SECCNTV) restarts it and
 * raises the second interrupt, served at once. A period write resets the
 * counter (hal_rtc_lld.c / rtc.c's comments: "resets SECCNT"). */
#define ILRC_HZ 33601u
static uint64_t cyc_acc;   /* ILRC cycles x 1000 since the counter restarted */
void rtc_lld_set_period(RTCDriver *rtcp, uint32_t period) {
    rtcp->period = period;
    cyc_acc = 0;
    sim_rtc_regs.SECCNT = 0;
}
uint32_t rtc_lld_get_period(RTCDriver *rtcp) { return rtcp->period; }

static void sim_rtc_advance_1ms(void) {
    cyc_acc += ILRC_HZ;   /* ILRC_HZ cycles per 1000 ms */
    uint32_t cnt = (uint32_t)(cyc_acc / 1000u);
    if (cnt > RTCD1.period) {
        cyc_acc -= (uint64_t)(RTCD1.period + 1u) * 1000u;
        sim_rtc_regs.SECCNT = (uint32_t)(cyc_acc / 1000u);
        lld_time++;                                   /* the LLD ISR: rtc_time++ */
        if (RTCD1.callback) RTCD1.callback(&RTCD1, RTC_EVENT_SECOND);
    } else {
        sim_rtc_regs.SECCNT = cnt;
    }
}

/* ------------------------------------------------------------------ */
/* The PCF8563 on the bit-banged I2C                                   */
/* ------------------------------------------------------------------ */
static time_t   pcf_epoch;     /* the PCF's time at pcf_ms0 */
static uint64_t pcf_ms0;
static uint8_t  pcf_ctl0;
static uint8_t  pcf_ptr;
static bool     pcf_vl;
static int      pcf_fail_next;  /* fail this many transactions from now (NACK/deadline) */
static unsigned pcf_xfers_total, pcf_xfers_failed, pcf_reads_ok_calendar;

static time_t pcf_now(void) { return pcf_epoch + (time_t)((sim_ms - pcf_ms0) / 1000u); }
static uint8_t bcd(unsigned v) { return (uint8_t)(((v / 10) << 4) | (v % 10)); }
static unsigned unbcd(uint8_t v) { return (unsigned)((v >> 4) * 10 + (v & 0x0F)); }

static uint8_t pcf_reg(uint8_t r) {
    time_t t = pcf_now();
    struct tm tm;
    gmtime_r(&t, &tm);
    switch (r) {
    case 0: return pcf_ctl0;
    case 1: return 0;
    case 2: return (uint8_t)(bcd((unsigned)tm.tm_sec) | (pcf_vl ? 0x80 : 0));
    case 3: return bcd((unsigned)tm.tm_min);
    case 4: return bcd((unsigned)tm.tm_hour);
    case 5: return bcd((unsigned)tm.tm_mday);
    case 6: return (uint8_t)tm.tm_wday;
    case 7: return bcd((unsigned)tm.tm_mon + 1);
    case 8: return bcd((unsigned)(tm.tm_year % 100));
    default: return 0;
    }
}

void i2cStart(I2CDriver *i2cp, const I2CConfig *c) { (void)c; i2cp->started = 1; }
void i2cStop(I2CDriver *i2cp) { i2cp->started = 0; }

msg_t i2cMasterTransmitTimeout(I2CDriver *i2cp, i2caddr_t addr, const uint8_t *tx, size_t ntx,
                               uint8_t *rx, size_t nrx, sysinterval_t timeout) {
    (void)timeout;
    pcf_xfers_total++;
    if (!i2cp->started || addr != 0x51) { pcf_xfers_failed++; return MSG_TIMEOUT; }
    if (pcf_fail_next > 0) { pcf_fail_next--; pcf_xfers_failed++; return MSG_TIMEOUT; }
    if (ntx >= 1) pcf_ptr = tx[0];
    if (nrx == 0) {
        /* write: an 8-byte time write at 0x02 sets the calendar and clears VL */
        if (pcf_ptr == 0x02 && ntx == 8) {
            struct tm tm = {0};
            tm.tm_sec  = (int)unbcd(tx[1] & 0x7F);
            tm.tm_min  = (int)unbcd(tx[2] & 0x7F);
            tm.tm_hour = (int)unbcd(tx[3] & 0x3F);
            tm.tm_mday = (int)unbcd(tx[4] & 0x3F);
            tm.tm_mon  = (int)unbcd(tx[6] & 0x1F) - 1;
            tm.tm_year = (int)unbcd(tx[7]) + 100;
            pcf_epoch = timegm(&tm);
            pcf_ms0   = sim_ms;
            pcf_vl    = false;
        } else if (pcf_ptr == 0x00 && ntx == 2) {
            pcf_ctl0 = tx[1];
        }
        return MSG_OK;
    }
    for (size_t i = 0; i < nrx; i++) rx[i] = pcf_reg((uint8_t)(pcf_ptr + i));
    if (pcf_ptr == 0x02 && nrx == 7 && !pcf_vl) pcf_reads_ok_calendar++;
    return MSG_OK;
}

/* ------------------------------------------------------------------ */
/* The rest of the board, as rtc.c sees it                              */
/* ------------------------------------------------------------------ */
usbstate_t usbGetDriverStateI(USBDriver *u) { (void)u; return sim_usb; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)TIME_MS2I(sim_ms); }
uint32_t timer_read32(void) { return (uint32_t)sim_ms; }
uint32_t last_input_activity_elapsed(void) { return 0; }
bool lcd_blit_busy(void) { return false; }
bool lcd_blit_wait(void) { return true; }
bool display_splash_done(void) { return sim_ms >= 2500; }   /* the splash ends ~2.5 s after boot */
bool display_bus_idle(void) { return true; }
void display_defer_pass(void) {}
uint16_t kb_eeconfig_get_rtc_period(void) { return 33600; }
void rtc_persist_propose(uint16_t period, uint8_t path) { (void)period; (void)path; }
void rtc_persist_task(void) {}
sysinterval_t sleep_pass_ticks(void) { return 0; }
bool sleep_recovering(void) { return false; }
bool sn32f2xx_led_committed_dark(void) { return false; }
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void watchdog_record_leave(uint32_t *previous) { (void)previous; }

/* ------------------------------------------------------------------ */
/* The main loop                                                        */
/* ------------------------------------------------------------------ */
static uint64_t last_hk, passes, rtc_task_calls;
static void pass(void) {
    rtc_fast_task();                      /* every pass (ak820pro.c:607) */
    if (sim_ms - last_hk >= 100) {        /* the 10 Hz housekeeping (ak820pro.c:648) */
        last_hk = sim_ms;
        rtc_task(); rtc_task_calls++;
    }
    rtc_pass_mark(); passes++;            /* sleep_task(), at each pass's end */
}
static void run_ms(uint64_t ms) {
    for (uint64_t i = 0; i < ms; i++) {
        sim_ms++;
        sim_rtc_advance_1ms();
        if (sim_ms % 3 == 0) pass();      /* ~335 passes a second */
    }
}

static int fails;
#define CHECK(c, ...) do { if (!(c)) { printf("  FAIL %s:%d: %s -- ", __FILE__, __LINE__, #c); printf(__VA_ARGS__); printf("\n"); fails++; } else { printf("  ok   %s\n", #c); } } while (0)

static uint8_t acq_state_now(void) { uint8_t p4[28] = {0}; rtc_status_fill_page4(p4); return p4[8]; }
static time_t lld_epoch(void) { return lld_time; }
static void fmt(time_t t, char *buf, size_t n) { struct tm tm; gmtime_r(&t, &tm); strftime(buf, n, "%Y-%m-%d %H:%M:%S", &tm); }

static void boot(int fail_first) {
    /* PCF healthy, set to 2026-10-31 14:23:17.400 at power-on (phase offset) */
    struct tm tm = { .tm_year = 126, .tm_mon = 9, .tm_mday = 31, .tm_hour = 14, .tm_min = 23, .tm_sec = 17 };
    pcf_epoch = timegm(&tm);
    pcf_ms0   = 0;
    sim_ms    = 400;      /* the board starts 400 ms into the PCF's second */
    pcf_ms0   = 0;
    pcf_vl    = false;
    pcf_fail_next = fail_first;
    rtc_init();           /* keyboard_post_init_kb: the one seed */
}

static void report(const char *when) {
    rtc_time_t t; bool ok = rtc_get_time(&t);
    rtc_stamp_t s; bool now_ok = rtc_now(&s);
    char a[32], b[32];
    fmt(lld_epoch(), a, sizeof a); fmt(pcf_now(), b, sizeof b);
    printf("  [%s] t=%llus rtc_get_time=%d rtc_now=%d acq_state=%u  LLD calendar=%s  PCF=%s  xfers=%u (failed %u, good calendar reads %u) passes=%llu rtc_task=%llu\n",
           when, (unsigned long long)(sim_ms / 1000), ok, now_ok, acq_state_now(), a, b,
           pcf_xfers_total, pcf_xfers_failed, pcf_reads_ok_calendar, (unsigned long long)passes, (unsigned long long)rtc_task_calls);
    if (ok) printf("           rtc_get_time -> %04u-%02u-%02u %02u:%02u:%02u\n", t.year, t.month, t.day, t.hours, t.minutes, t.seconds);
}

static int scenario_control(void) {
    printf("== control: the boot read succeeds\n");
    boot(0);
    run_ms(120000);
    report("120 s");
    rtc_time_t t;
    CHECK(rtc_get_time(&t), "clock should be valid");
    CHECK(acq_state_now() == 2, "acquisition should be DONE (2), is %u", acq_state_now());
    long d = (long)(lld_epoch() - pcf_now());
    CHECK(d >= -1 && d <= 1, "LLD vs PCF %ld s", d);
    return 0;
}

static int scenario_bug(int fixed_expect) {
    printf("== %s: only the first PCF transaction (rtc_init's seed) fails; the PCF is fine after; on battery, no host\n",
           fixed_expect ? "first" : "bug");
    boot(1);
    report("boot");
    unsigned failed_at_boot = pcf_xfers_failed;
    run_ms(120000);
    report("120 s");
    rtc_time_t t;
    long d = (long)(lld_epoch() - pcf_now());
    if (!fixed_expect) {
        CHECK(failed_at_boot == 1, "exactly one failed transaction at boot");
        CHECK(pcf_reads_ok_calendar >= 1, "the discipline read the PCF successfully afterwards");
        CHECK(d >= -2 && d <= 2, "the discipline put the PCF's calendar into the LLD (LLD - PCF = %ld s)", d);
        CHECK(!rtc_get_time(&t), "BUG: rtc_get_time() still false although the LLD has the right time");
        rtc_stamp_t s;
        CHECK(!rtc_now(&s), "BUG: rtc_now() false, so board_ms_now() fails too");
        CHECK(acq_state_now() == 0, "BUG: boot acquisition stuck in ACQ_WAIT_SPLASH (0), is %u", acq_state_now());
    } else {
        CHECK(rtc_get_time(&t), "FIXED: clock valid after the retry");
        CHECK(acq_state_now() == 2, "FIXED: acquisition DONE (2), is %u", acq_state_now());
        CHECK(d >= -1 && d <= 1, "FIXED: LLD vs PCF %ld s", d);
        return 0;
    }

    /* Six hours on battery with no host: still blank. */
    run_ms(6ull * 3600ull * 1000ull);
    report("6 h");
    d = (long)(lld_epoch() - pcf_now());
    CHECK(!rtc_get_time(&t), "BUG: still unset after 6 h of a healthy PCF");
    CHECK(d >= -2 && d <= 2, "LLD tracks the PCF all along (LLD - PCF = %ld s)", d);

    /* A deep sleep and its wake: the coarse read sets the calendar from the
     * PCF, then acq_rearm() aborts the acquisition because rtc_valid is false. */
    printf("  -- a deep sleep of 300 s and its wake\n");
    CHECK(rtc_sleep_ok(), "sleep allowed (WAIT_SPLASH with !rtc_valid does not hold the board awake)");
    CHECK(rtc_sleep_prepare(), "pre-sleep read admitted");
    uint64_t slept_ms = 300000; uint32_t counted = 261;   /* the ILRC ~13% slow asleep */
    sim_ms += slept_ms;                                   /* asleep: no ticks served */
    rtc_account_sleepI(counted);
    rtc_wake_beginI(counted);
    rtc_pass_mark();
    rtc_wake_allow();
    rtc_wake_gauge_taken();
    run_ms(5000);
    report("after wake");
    d = (long)(lld_epoch() - pcf_now());
    CHECK(rtc_wake_acq_result() == 3, "BUG: the wake's acquisition ABORTED (3) by acq_rearm(), is %u", rtc_wake_acq_result());
    CHECK(!rtc_get_time(&t), "BUG: still unset after the wake although the coarse read set the calendar");
    CHECK(d >= -1 && d <= 1, "LLD set from the PCF by the coarse read (LLD - PCF = %ld s)", d);

    /* Only a host set brings it back. */
    printf("  -- a host's RTC_SET_TIME_MS (raw HID or lock-LED type 4)\n");
    rtc_time_t h; time_t hn = pcf_now(); struct tm tm; gmtime_r(&hn, &tm);
    h.year = (uint16_t)(tm.tm_year + 1900); h.month = (uint8_t)(tm.tm_mon + 1); h.day = (uint8_t)tm.tm_mday;
    h.hours = (uint8_t)tm.tm_hour; h.minutes = (uint8_t)tm.tm_min; h.seconds = (uint8_t)tm.tm_sec; h.weekday = (uint8_t)tm.tm_wday;
    int16_t off = 0;
    uint8_t st = rtc_set_time_ms(&h, 0, 0, 0x7FFF, &off);
    CHECK(st == 0, "host set STEPPED (0), got %u", st);
    CHECK(rtc_get_time(&t), "a host set is what makes the clock valid");
    return 0;
}

int main(int argc, char **argv) {
    setenv("TZ", "UTC0", 1);   /* newlib with no TZ: UTC */
    tzset();
    const char *which = argc > 1 ? argv[1] : "all";
    if (!strcmp(which, "control")) scenario_control();
    else if (!strcmp(which, "bug")) scenario_bug(0);
    else if (!strcmp(which, "first")) scenario_bug(1);
    else { scenario_control(); printf("\n(new process needed for the bug scenario: rtc.c's statics)\n"); }
    printf("%s (%d failed checks)\n", fails ? "FAILURES" : "ALL CHECKS PASSED", fails);
    return fails ? 1 : 0;
}
