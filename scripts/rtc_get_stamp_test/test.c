/* RTC_GET_TIME's reply from one stamp (plans/AUDIT-2026-10-31.md, F-009;
 * first written as the audit's verify-006).
 *
 * What is real here (compiled from the firmware tree by path, never edited):
 *   - lib/chibios-contrib/.../SN32F2xx/RTC/hal_rtc_lld.c, whole: rtc_time,
 *     rtc_lld_get_time() (sample under the lock, THEN rtc_decode ->
 *     localtime_r), the RTC IRQ handler (rtc_time++ and the callback),
 *     rtc_lld_set_time/period/callback;
 *   - lib/chibios/os/hal/src/hal_rtc.c, whole: rtcGetTime, rtcSetCallback,
 *     the RTCDateTime <-> struct tm conversions;
 *   - rtc/rtc.c, extracted verbatim at build time: chibiostime_to_rtc(),
 *     rtc_get_time(), rtc_now(), put16/put32, rtc_status_fill_page1(),
 *     rtc_status_fill();
 *   - hid_protocol.c, extracted verbatim: rtc_read_into();
 *   - time-util-ak820pro/ak820ctl.c, extracted verbatim: board_sod(), the
 *     host's decode (the Rust daemon is an oracle-parity port of it).
 *
 * What is modelled:
 *   - the SN32 RTC block: SECCNT counts 0..SECCNTV over one board second and
 *     the second interrupt fires at the wrap; IC is write-1-to-clear;
 *   - time: the board clock only advances while a calendar decode
 *     (localtime_r) runs, by the decode cost per decode -- the wall time one
 *     decode takes on the M0 under the row ISR. When the advance crosses a
 *     second boundary the real IRQ handler is called at that point
 *     (interrupts are enabled: rtc_lld_get_time() has already dropped its
 *     lock);
 *   - rtc_second_cb: only its `rtc_seconds_count++`; the rest of it schedules
 *     reloads/estimates and touches neither rtc_time nor the count;
 *   - the reply as it was before the fix (two samples: rtc_get_time() for the
 *     calendar, a second stamp for the count), which must still tear here, so
 *     a harness that can no longer see a tear fails instead of passing.
 */
#include "hal.h"
#include "rtc.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

/* ---------------- the simulated SN32 RTC ---------------- */
static int64_t     sim_ns;              /* board-true time, ns since the Unix epoch */
static int64_t     sim_decode_ns = 300000;
static SN_RTC_Type sim_regs;
static int         sim_locked, sim_pending;
static int64_t     sim_last_access_ns;  /* when SN_RTC was last read through SN_RTC */
static unsigned    sim_ticks;

void sim_rtc_irq_handler(void);         /* the real OSAL_IRQ_HANDLER(SN32_RTC_HANDLER) */

SN_RTC_Type *sim_rtc_regs(void) {
    int64_t frac = sim_ns % 1000000000LL;
    sim_regs.SECCNT = (uint32_t)((frac * (int64_t)(sim_regs.SECCNTV + 1)) / 1000000000LL);
    sim_last_access_ns = sim_ns;
    return &sim_regs;
}
static void sim_run_isr(void) {
    sim_regs.IC = 0;
    sim_rtc_irq_handler();
    sim_regs.RIS &= ~sim_regs.IC;       /* write-1-to-clear */
}
syssts_t sim_lock(void) { syssts_t s = (syssts_t)sim_locked; sim_locked = 1; return s; }
void sim_restore(syssts_t s) {
    sim_locked = (int)s;
    if (!sim_locked && sim_pending) { sim_pending = 0; sim_run_isr(); }
}
static void sim_tick(void) {
    sim_ticks++;
    sim_regs.RIS |= mskRTC_SECIF;
    if (sim_locked) sim_pending = 1; else sim_run_isr();
}
static void sim_advance(int64_t dt) {
    int64_t end = sim_ns + dt;
    while (end / 1000000000LL > sim_ns / 1000000000LL) {   /* a boundary in (now, end] */
        sim_ns = (sim_ns / 1000000000LL + 1) * 1000000000LL;
        sim_tick();
    }
    sim_ns = end;
}
/* hal_rtc_lld.c is compiled with -Dlocaltime_r=sim_localtime_r: the decode
 * of the value already sampled, and the time the decode takes on the board. */
struct tm *sim_localtime_r(const time_t *t, struct tm *out) {
    struct tm *r = localtime_r(t, out);
    sim_advance(sim_decode_ns);
    return r;
}

/* ---------------- rtc.c's state the extracted code reads ---------------- */
static volatile uint32_t rtc_seconds_count = 0;
static uint16_t stale_count    = 0;
static uint16_t i2c_fail_count = 0;
static uint32_t i2c_max_cycles = 0;
static uint32_t last_sync_secs = 0;
static bool     host_synced    = true;
static int16_t  last_host_offset_ms = 0;
static uint32_t P_nom = 33599;
enum { SLEW_IDLE = 0, SLEW_START = 1, SLEW_RUN = 2 };
static volatile uint8_t  slew_state = SLEW_IDLE;
static volatile uint16_t window_rejects = 0;
static int16_t  sof_bias_ppm = 0;
static uint8_t  ref_state = 0;
static uint16_t ref_transitions = 0;
static uint16_t deferred_passes = 0;
static bool     pcf_backoff = false;
static bool     pcf_maybe_stopped = false;
static bool     pcf_boot_stopped = false;
static volatile uint16_t lat_min = 0xFFFF, lat_max = 0, lat_n = 0;
static volatile uint32_t lat_sum = 0;
static volatile uint8_t  usb_active_mirror = 0;
static volatile uint8_t  fn_valid = 0;
static volatile uint32_t sof_frames_total = 0;
static volatile uint8_t  sof_epoch = 0;
static volatile uint16_t d_zero = 0, d_reject = 0;
#define D_RING_N 14
static volatile uint16_t d_ring[D_RING_N];
static volatile uint8_t  d_ring_i = 0;
static bool rtc_valid = true;
void rtc_status_fill_page4(uint8_t *out) { (void)out; }
static bool acq_state_done(void) { return true; }

static void sim_second_cb(RTCDriver *rtcp, rtcevent_t event) {
    (void)rtcp; (void)event;
    rtc_seconds_count++;                 /* rtc.c:568 */
}

#include "x_rtc.inc"            /* rtc.c, verbatim */
#include "x_hid_protocol.inc"   /* hid_protocol.c's rtc_read_into, verbatim */
#include "x_ak820ctl.inc"       /* ak820ctl.c's board_sod, verbatim */

/* The reply before the fix, NOT firmware code: the calendar from
 * rtc_get_time(), the count from page 1's own stamp. */
static void rtc_read_into_two_samples(uint8_t *data) {
    rtc_time_t t = {0};
    bool ok = rtc_get_time(&t);
    data[3] = ok ? 1 : 0;
    data[4] = (uint8_t)(t.year >= 2000 ? t.year - 2000 : 0);
    data[5] = t.month; data[6] = t.day; data[7] = t.weekday;
    data[8] = t.hours; data[9] = t.minutes; data[10] = t.seconds;
    rtc_status_fill(1, &data[11]);
}

/* ---------------- harness ---------------- */
static const int64_t BASE_S = 1793448000LL;   /* 2026-10-31 12:00:00 UTC, a board second boundary */

static void board_set(int64_t start_ns) {
    time_t whole = (time_t)(start_ns / 1000000000LL);
    struct tm tm;
    gmtime_r(&whole, &tm);
    RTCDateTime dt;
    rtcConvertStructTmToDateTime(&tm, 0, &dt);
    rtc_lld_set_time(&RTCD1, &dt);            /* real: rtc_encode -> mktime */
    sim_ns = start_ns;
    sim_regs.RIS = 0;
    sim_pending = 0;
    stale_count = 0;
}

/* One GET starting at start_ns; returns the host's decoded error in ms
 * against the board's true time at the moment the tail's SECCNT was read. */
static double one_get(int64_t start_ns, int firmware, uint8_t *rep) {
    board_set(start_ns);
    memset(rep, 0, 32);
    rep[0] = 0x07; rep[1] = 0x10; rep[2] = 0x02;
    if (firmware) rtc_read_into(rep);
    else          rtc_read_into_two_samples(rep);
    int64_t truth_ns = sim_last_access_ns;
    double board = board_sod(rep);
    double truth = (double)(truth_ns % (86400LL * 1000000000LL)) / 1e9;
    return (board - truth) * 1000.0;
}

int main(int argc, char **argv) {
    setenv("TZ", "UTC0", 1);   /* newlib on the board has no TZ: UTC */
    tzset();
    if (argc > 1) sim_decode_ns = atoll(argv[1]) * 1000LL;   /* microseconds */

    rtcInit();                                 /* real: rtc_lld_init */
    rtc_lld_set_period(&RTCD1, P_nom);         /* steady state: active == nominal */
    rtcSetCallback(&RTCD1, sim_second_cb);
    if (sizeof(time_t) != 8) { printf("time_t is not 64-bit\n"); return 2; }

    int fails = 0;
    uint8_t rep[32];
    printf("decode cost per localtime_r: %lld us (the gap between the two samples)\n",
           (long long)(sim_decode_ns / 1000));

    /* 1. A GET just before a boundary, where the reply used to tear. */
    const int64_t probes_us[] = {-400000, -1000, -400, -299, -200, -100, -1, 0, 1, 200};
    for (unsigned i = 0; i < sizeof probes_us / sizeof probes_us[0]; i++) {
        int64_t start = BASE_S * 1000000000LL + probes_us[i] * 1000LL;
        double e  = one_get(start, 1, rep);
        unsigned cnt = rep[12] | rep[13] << 8 | rep[14] << 16 | (unsigned)rep[15] << 24;
        printf("GET %+7lld us from 12:00:00  reply %02u:%02u:%02u cnt %5u ok %u proto %u  error %+8.3f ms",
               (long long)probes_us[i], rep[8], rep[9], rep[10], cnt, rep[3], rep[11], e);
        double eo = one_get(start, 0, rep);
        printf("   | two samples: %02u:%02u:%02u error %+9.3f ms\n", rep[8], rep[9], rep[10], eo);
    }

    /* 2. No stamp: the second's interrupt pending and never served, so every
     * one of rtc_now()'s tries sees SECIF. The reply must say unset (which
     * the hosts skip) and carry zeros, not a calendar or a stale count. */
    board_set(BASE_S * 1000000000LL + 250000000LL);
    sim_regs.RIS |= mskRTC_SECIF;
    memset(rep, 0xAA, 32);
    rep[0] = 0x07; rep[1] = 0x10; rep[2] = 0x02;
    rtc_read_into(rep);
    bool zeros = true;
    for (int i = 4; i <= 10; i++) zeros = zeros && rep[i] == 0;
    for (int i = 12; i <= 15; i++) zeros = zeros && rep[i] == 0;
    printf("no stamp (SECIF pending throughout): ok %u, fields %s, stale_count %u, board_sod %.0f\n", rep[3],
           zeros ? "zero" : "NOT zero", stale_count, board_sod(rep));
    if (rep[3] != 0 || !zeros || board_sod(rep) >= 0) { printf("FAIL: a reply with no stamp is not plainly unset\n"); fails++; }
    sim_regs.RIS &= ~mskRTC_SECIF;

    /* 3. Every phase of a second at 1 us. */
    long wrong = 0, unset = 0, torn_old = 0, n = 0;
    int64_t torn_lo = INT64_MAX, torn_hi = INT64_MIN;
    double worst = 0;
    for (int64_t us = -500000; us < 500000; us++) {
        int64_t start = BASE_S * 1000000000LL + us * 1000LL;
        n++;
        double e = one_get(start, 1, rep);
        if (!rep[3]) unset++;
        else if (fabs(e) >= 1.0) wrong++;
        else if (fabs(e) > worst) worst = fabs(e);
        double eo = one_get(start, 0, rep);
        if (fabs(eo + 1000.0) < 1.0) {
            torn_old++;
            if (us < torn_lo) torn_lo = us;
            if (us > torn_hi) torn_hi = us;
        }
    }
    printf("\nsweep: %ld GETs, one every 1 us across a second\n", n);
    printf("  firmware:    %ld wrong, %ld unset; worst |error| %.3f ms\n", wrong, unset, worst);
    printf("  two samples: %ld read exactly 1 s low (1 in %.0f), GET starts %lld..%lld us from the boundary\n",
           torn_old, torn_old ? (double)n / torn_old : 0.0, (long long)torn_lo, (long long)torn_hi);
    if (wrong || unset) { printf("FAIL: the firmware's reply is wrong or unset\n"); fails++; }
    /* The old window is TWO decodes wide: a boundary inside rtc_now()'s first
     * try makes it retry, and the retry's count is still paired with
     * rtc_get_time()'s earlier second. If the model stops tearing there, the
     * harness has lost the effect it exists to see. */
    long long want_lo = -2 * (sim_decode_ns / 1000);
    if (torn_old == 0 || torn_lo != want_lo || torn_hi != -1) {
        printf("FAIL: the two-sample model no longer tears at %lld..-1 us: the harness is blind\n", want_lo);
        fails++;
    }
    printf(fails ? "RESULT: FAIL\n" : "RESULT: PASS (one stamp: no tear; the old reply still tears in the model)\n");
    return fails ? 1 : 0;
}
