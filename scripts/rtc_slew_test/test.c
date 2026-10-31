/* Host test of rtc.c's slew (rtc_second_cb, SLEW_START / SLEW_RUN), against
 * a model of the SN32 RTC with the measured T0.1 semantics
 * (history/clock-sync/phase-0-facts.md): a SECCNTV write resets SECCNT to 0
 * at once; a match restarts the count; an interval is SECCNTV + 1 cycles
 * from a match (the firmware's own `next = L + P_nom + 1` convention).
 *
 * The real rtc.c is compiled in by path (never edited). The real
 * rtc_set_time_ms() starts the slew, exactly as a host's RTC_SET_TIME_MS (or
 * a lock-LED type 4 frame) does; the real rtc_second_cb() is called at each
 * match, L cycles after it, with SECCNT reading L, as the hardware does.
 *
 * Measured: the shift of the match times after the slew, against the D
 * cycles rtc_set_time_ms asked for (plans/AUDIT-2026-10-31.md, F-026; first
 * written as the audit's verify-021). Before the fix the compensated start
 * stayed in the register and every untouched interval ran L short, so a long
 * slew overshot by (untouched intervals) x L. Now the start is compensated
 * only when the next tick rewrites it: the error is -L (the restore) when it
 * is, -2L (the start's interval and the restore) when it is not, whatever the
 * slew's length. Also checked: the
 * firmware's own interval bookkeeping (interval_cycles) agrees with the
 * model, interval by interval, so the model is the firmware's own belief of
 * the hardware, not an assumption of this test.
 */
#define RTC_AUTO_CALIBRATION
#define RTC_PERIOD_INITIAL 33600
#include "rtc/rtc.c"   /* the real one: run.sh puts the board's directory on the path */

#include <stdlib.h>

/* ---- the HAL and hardware model ------------------------------------------ */
sn_rtc_t   sim_rtc;
sn_usb_t   sim_usb;
nvic_t     sim_nvic;
I2CDriver  I2CD1;
RTCDriver  RTCD1;
USBDriver  USBD1;
volatile uint8_t loop_stall_mark;

static time_t sim_time;     /* the LLD's software seconds */
static int    sim_wrote;    /* a SECCNTV write this ISR */

void rtc_lld_set_period(RTCDriver *r, uint32_t p) {
    if (p > SN32_RTC_PERIOD_MAX) p = SN32_RTC_PERIOD_MAX;
    r->period       = p;
    sim_rtc.SECCNTV = p;
    sim_rtc.SECCNT  = 0;    /* T0.1: any SECCNTV write resets SECCNT */
    sim_wrote       = 1;
}
uint32_t rtc_lld_get_period(RTCDriver *r) { return r->period; }
void rtc_lld_add_secondsI(RTCDriver *r, uint32_t s) { (void)r; sim_time += (time_t)s; }

/* ChibiOS hal_rtc.c's conversions (RTC_BASE_YEAR 1980). */
void rtcConvertDateTimeToStructTm(const RTCDateTime *ts, struct tm *tm, uint32_t *ms) {
    memset(tm, 0, sizeof *tm);
    tm->tm_year  = (int)ts->year + (int)(RTC_BASE_YEAR - 1900U);
    tm->tm_mon   = (int)ts->month - 1;
    tm->tm_mday  = (int)ts->day;
    tm->tm_isdst = (int)ts->dstflag;
    tm->tm_wday  = (int)ts->dayofweek - 1;
    if (tm->tm_wday == 7) tm->tm_wday = 0;
    int sec = (int)ts->millisecond / 1000;
    tm->tm_hour = sec / 3600; sec %= 3600;
    tm->tm_min  = sec / 60;
    tm->tm_sec  = sec % 60;
    if (ms) *ms = ts->millisecond % 1000U;
}
void rtcConvertStructTmToDateTime(const struct tm *tm, uint32_t ms, RTCDateTime *ts) {
    ts->year      = (uint32_t)tm->tm_year - (RTC_BASE_YEAR - 1900U);
    ts->month     = (uint32_t)tm->tm_mon + 1U;
    ts->day       = (uint32_t)tm->tm_mday;
    ts->dayofweek = (uint32_t)tm->tm_wday + 1U;
    if (ts->dayofweek == 7U) ts->dayofweek = 0U;
    ts->dstflag   = (uint32_t)tm->tm_isdst;
    ts->millisecond = (uint32_t)((tm->tm_hour * 3600 + tm->tm_min * 60 + tm->tm_sec) * 1000) + ms;
}
void rtcSetTime(RTCDriver *r, const RTCDateTime *dt) {
    (void)r; struct tm tm; rtcConvertDateTimeToStructTm(dt, &tm, NULL); sim_time = mktime(&tm);
}
void rtcGetTime(RTCDriver *r, RTCDateTime *dt) {
    (void)r; struct tm tm; localtime_r(&sim_time, &tm); rtcConvertStructTmToDateTime(&tm, 0, dt);
}
void rtcSetCallback(RTCDriver *r, rtccb_t cb) { r->callback = cb; }

/* Never reached on this path; defined so the binary links. */
void  i2cStart(I2CDriver *d, const I2CConfig *c) { (void)d; (void)c; }
void  i2cStop(I2CDriver *d) { (void)d; }
msg_t i2cMasterTransmitTimeout(I2CDriver *d, i2caddr_t a, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx, sysinterval_t t) {
    (void)d; (void)a; (void)tx; (void)ntx; (void)rx; (void)nrx; (void)t; abort();
}
int usbGetDriverStateI(USBDriver *u) { (void)u; return 0; }
uint32_t last_input_activity_elapsed(void) { return 0; }
uint32_t timer_read32(void) { return 0; }
uint32_t timer_elapsed32(uint32_t t) { (void)t; return 0; }
void wait_us(uint32_t us) { (void)us; }
bool sn32f2xx_led_committed_dark(void) { return false; }
bool display_splash_done(void) { return true; }
bool display_bus_idle(void) { return true; }
void display_defer_pass(void) {}
bool lcd_blit_busy(void) { return false; }
bool lcd_blit_wait(void) { return true; }
uint16_t kb_eeconfig_get_rtc_period(void) { return 0; }
void rtc_persist_propose(uint16_t period, uint8_t path) { (void)period; (void)path; }
void rtc_persist_task(void) {}
sysinterval_t sleep_pass_ticks(void) { return 0; }
bool sleep_recovering(void) { return false; }
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void watchdog_record_leave(uint32_t *previous) { (void)previous; }

/* ---- the timeline ---------------------------------------------------------- */
static int64_t t_match;         /* absolute cycle of the latest match */
static int     model_mismatch;  /* firmware's interval_cycles != the model's */

/* One match: the ISR runs L cycles after it (SECCNT reads L), the LLD's
 * handler bumps its seconds and calls the board's callback. Returns the
 * interval that this match starts, as the hardware model times it. */
static int64_t tick(uint32_t L) {
    sim_rtc.SECCNT = L;
    sim_rtc.RIS    = 0;
    sim_wrote      = 0;
    sim_time++;                                     /* hal_rtc_lld.c: rtc_time++ */
    RTCD1.callback(&RTCD1, RTC_EVENT_SECOND);       /* rtc_second_cb */
    int64_t len = sim_wrote ? (int64_t)L + sim_rtc.SECCNTV + 1 : (int64_t)sim_rtc.SECCNTV + 1;
    if ((int64_t)interval_cycles != len) model_mismatch++;
    t_match += len;
    return len;
}

typedef struct { long err; long D; unsigned N; int r; long writes; } result_t;

static result_t run(uint32_t P, int off_ms, uint32_t L) {
    /* A synced board in steady state, register == P_nom == P. */
    P_nom = P;
    rtc_lld_set_period(&RTCD1, P);
    RTCD1.callback = rtc_second_cb;
    slew_state = SLEW_IDLE; reload_pending = false;
    rtc_valid = true; host_synced = true;
    usb_active_mirror = 0;
    /* model_mismatch accumulates over every run */
    struct tm tm0 = { .tm_year = 2026 - 1900, .tm_mon = 9, .tm_mday = 31, .tm_hour = 12 };
    sim_time = mktime(&tm0);
    t_match = 0;
    for (int i = 0; i < 3; i++) tick(L);            /* steady: no writes */

    /* The host's set lands 10000 cycles into the current interval. */
    int64_t t_call = t_match + 10000;
    sim_rtc.SECCNT = 10000;
    rtc_stamp_t s;
    if (!rtc_now(&s)) { printf("rtc_now failed\n"); exit(2); }
    int64_t frac_ms = 1000 - (int64_t)(s.period_active + 1 - s.cnt) * 1000 / (int64_t)(P_nom + 1);
    int64_t total   = frac_ms + off_ms;                             /* target - board second start, ms */
    int64_t whole   = total >= 0 ? total / 1000 : -((-total + 999) / 1000);
    time_t e_t = sim_time + (time_t)whole;
    uint16_t ms = (uint16_t)(total - whole * 1000);
    struct tm tm_t; localtime_r(&e_t, &tm_t);
    rtc_time_t tgt = { .seconds = (uint8_t)tm_t.tm_sec, .minutes = (uint8_t)tm_t.tm_min,
                       .hours = (uint8_t)tm_t.tm_hour, .day = (uint8_t)tm_t.tm_mday,
                       .weekday = (uint8_t)tm_t.tm_wday, .month = (uint8_t)(tm_t.tm_mon + 1),
                       .year = (uint16_t)(tm_t.tm_year + 1900) };
    int16_t before = 0;
    uint16_t w0 = reload_writes;
    uint8_t st = rtc_set_time_ms(&tgt, ms, RTC_SETF_SKIP_PCF, 0x7FFF, &before);
    if (st != RTC_SET_SLEWING || before != off_ms) {
        printf("set returned %u, offset %d (wanted SLEWING, %d)\n", st, before, off_ms); exit(2);
    }
    result_t res = { 0 };
    res.N = slew_left; res.r = slew_r;
    int64_t D = (int64_t)off_ms * (int64_t)(P_nom + 1) / 1000;     /* as rtc_set_time_ms computes it */
    res.D = (long)D;
    (void)t_call;

    /* The interval the call landed in runs on unchanged; then N slew
     * intervals, the restore, and steady ones. 80 ticks is past any N. */
    int64_t t_start = t_match;                      /* the match that sees SLEW_START */
    const int K = 80;
    for (int i = 0; i < K; i++) tick(L);
    if (slew_state != SLEW_IDLE) { printf("slew still running\n"); exit(2); }
    int64_t nominal = t_start + (int64_t)K * (P + 1);
    int64_t applied = nominal - t_match;            /* + : intervals shortened in total */
    res.err = (long)(applied - D);
    res.writes = (long)(uint16_t)(reload_writes - w0);
    return res;
}

int main(void) {
    setenv("TZ", "UTC", 1); tzset();
    const uint32_t P = 33500;
    const int offs[] = { 10, 20, 30, 50, 100, 204, 499, -10, -30, -50, -204, -499 };
    const uint32_t Ls[] = { 0, 2, 7, 30 };
    int fails = 0;
    printf("P_nom=%u, 1 cycle = %.1f us. err = applied - D; design budget = -L (the restore)\n", P, 1e6 / (P + 1));
    for (unsigned i = 0; i < sizeof offs / sizeof *offs; i++) {
        for (unsigned j = 0; j < sizeof Ls / sizeof *Ls; j++) {
            result_t r = run(P, offs[i], Ls[j]);
            /* The start is compensated when the next tick rewrites the register. */
            bool comp = r.N == 1 || (r.N == 2 && r.r != 0);
            long want = comp ? -(long)Ls[j] : -2 * (long)Ls[j];
            printf("off %+4d ms  N=%2u r=%+d writes=%ld  L=%2u  err %+5ld cycles (%+6.2f ms)  want %+ld (%s) %s\n",
                   offs[i], r.N, r.r, r.writes, Ls[j], r.err, r.err * 1000.0 / (P + 1), want,
                   comp ? "the restore's L" : "the start's and the restore's", r.err == want ? "ok" : "FAIL");
            if (r.err != want) fails++;
        }
    }
    printf("firmware interval_cycles vs model: %d mismatches\n", model_mismatch);
    if (model_mismatch) fails++;
    printf(fails ? "RESULT: FAIL (%d)\n" : "RESULT: PASS (every slew ends within two latencies, whatever its length)\n", fails);
    return fails ? 1 : 0;
}
