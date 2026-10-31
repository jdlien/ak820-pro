/* A PCF8563 left with STOP set by an MCU reset is released at boot
 * (plans/AUDIT-2026-10-31.md, F-005; first written as the audit's verify-018).
 *
 * Links the REAL keyboards/a_jazz/ak820pro/rtc/rtc.c, the REAL SN32 RTC LLD
 * (hal_rtc_lld.c: the calendar, the second ISR) and the REAL ChibiOS
 * hal_rtc.c, unedited, against:
 *  - a PCF8563 model that honours STOP (the divider chain frozen; release ->
 *    first increment 490 ms later, the clone's measured lead; a plain time
 *    write leaves the prescaler alone, phase-0 fact);
 *  - the SN32 RTC counter: SECCNT = ILRC cycles since the last restart, a
 *    write to SECCNTV restarts it, a match fires the LLD's real ISR body;
 *  - a main loop: rtc_fast_task() every ~3 ms pass, rtc_task() at 10 Hz,
 *    rtc_pass_mark() at each pass's end; off USB (the board on battery).
 *
 * The MCU reset is a real one for rtc.c: the process execv()s itself, so
 * every static in rtc.c, the LLD and hal_rtc.c starts from zero, while the
 * PCF model's registers and the true time are carried across in argv (the
 * PCF runs off the pack and keeps its registers through an MCU reset).
 *
 *   ./test stuck     reset inside the STOP window of a write run
 *   ./test control   reset after the run released STOP
 *
 * Before the fix the stuck case froze the clock: the seed took the stopped
 * PCF's time and the 60 s discipline snapped the board back to it every
 * minute until a host sync. Now the boot releases STOP, the board keeps time
 * behind by the time the PCF was stopped, and the PCF is stale until a host
 * sets the time. (The model's PCF advances only when it is read, so its time
 * is brought up to date before each look at it.)
 */
#include "hal.h"
#include "quantum.h"
#include "rtc/rtc.h"
#include <stdlib.h>
#include <unistd.h>
#include <inttypes.h>

/* ---- time ---------------------------------------------------------------- */
#define F_ILRC   33601ULL             /* P_nom 33600 (RTC_PERIOD_INITIAL) -> exactly 1 s a tick */
#define PASS_CYC (F_ILRC * 3 / 1000)  /* a ~3 ms main-loop pass */
static uint64_t cyc;                  /* true time, ILRC cycles since T_BASE */
static int64_t  T_BASE;               /* Unix time at cyc 0 */
static int64_t  true_epoch(void) { return T_BASE + (int64_t)(cyc / F_ILRC); }
static uint16_t true_ms(void)    { return (uint16_t)((cyc % F_ILRC) * 1000 / F_ILRC); }

/* ---- SN32 RTC registers -------------------------------------------------- */
SN_RTC_Type sim_rtc_regs;
SN_USB_Type sim_usb_regs;
NVIC_Type   sim_nvic;
USBDriver   USBD1 = { USB_STOP };   /* off USB: the cable out, the slider on BT */
I2CDriver   I2CD1;
static uint64_t rtc_restart;        /* the counter's last restart, cycles */
static uint32_t rtc_period;         /* SECCNTV in force */
static int      seccntv_pending;
int sim_seccntv_touch(void) { seccntv_pending = 1; return 0; }
static void apply_seccntv(void) {
    if (!seccntv_pending) return;
    seccntv_pending = 0;
    rtc_period  = sim_rtc_regs.SECCNTV_reg[0];
    rtc_restart = cyc;                       /* T0.1: a SECCNTV write restarts SECCNT */
}
int sim_seccnt_read(void) {
    apply_seccntv();
    sim_rtc_regs.SECCNT_reg[0] = (uint32_t)(cyc - rtc_restart);
    return 0;
}
static unsigned isr_count __attribute__((unused));
static void advance_to(uint64_t target) {
    apply_seccntv();
    for (;;) {
        uint64_t match = rtc_restart + (uint64_t)rtc_period + 1;
        if (!(sim_rtc_regs.CTRL & 1u) || match > target) break;
        cyc = match;
        rtc_restart = match;
        if (sim_rtc_regs.IE & mskRTC_SECIE) {
            sim_rtc_regs.RIS = mskRTC_SECIF;
            sim_sn32_rtc_handler();          /* the LLD's real handler: rtc_time++, then rtc.c's callback */
            sim_rtc_regs.RIS = 0;
            isr_count++;
            apply_seccntv();
        }
    }
    cyc = target;
}

/* ---- PCF8563 model ------------------------------------------------------- */
#define PCF_STOP 0x20
typedef struct { int64_t epoch; uint8_t ctl1, ctl2; int64_t next_inc; } pcf_t;
static pcf_t pcf;
static unsigned pcf_xfers_seen __attribute__((unused)), pcf_ctl_reads;
static uint8_t bcd(int v) { return (uint8_t)(((v / 10) << 4) | (v % 10)); }
static int     dec(uint8_t v) { return (v >> 4) * 10 + (v & 0x0F); }
static void pcf_advance(void) {
    if (pcf.ctl1 & PCF_STOP) return;          /* STOP: divider chain held, no increments */
    while ((int64_t)cyc >= pcf.next_inc) { pcf.epoch++; pcf.next_inc += (int64_t)F_ILRC; }
}
static void pcf_regs(uint8_t r[7]) {
    time_t e = (time_t)pcf.epoch; struct tm tm; gmtime_r(&e, &tm);
    r[0] = bcd(tm.tm_sec);            /* VL (bit 7) clear: STOP stops the divider, not the oscillator */
    r[1] = bcd(tm.tm_min); r[2] = bcd(tm.tm_hour); r[3] = bcd(tm.tm_mday);
    r[4] = (uint8_t)tm.tm_wday; r[5] = bcd(tm.tm_mon + 1); r[6] = bcd(tm.tm_year - 100);
}
static int64_t pcf_from_regs(const uint8_t r[7]) {
    struct tm tm = {0};
    tm.tm_sec = dec(r[0] & 0x7F); tm.tm_min = dec(r[1] & 0x7F); tm.tm_hour = dec(r[2] & 0x3F);
    tm.tm_mday = dec(r[3] & 0x3F); tm.tm_mon = dec(r[5] & 0x1F) - 1; tm.tm_year = 100 + dec(r[6]);
    return (int64_t)timegm(&tm);
}
static void pcf_write_ctl1(uint8_t v) {
    bool was = pcf.ctl1 & PCF_STOP, now = v & PCF_STOP;
    pcf.ctl1 = v;
    if (was && !now) pcf.next_inc = (int64_t)cyc + (int64_t)(F_ILRC * 490 / 1000);   /* release: first increment ~0.49 s on */
}
void i2cStart(I2CDriver *d, const I2CConfig *c) { (void)d; (void)c; }
void i2cStop(I2CDriver *d) { (void)d; }
msg_t i2cMasterTransmitTimeout(I2CDriver *d, uint16_t addr, const uint8_t *tx, size_t ntx,
                               uint8_t *rx, size_t nrx, sysinterval_t timeout) {
    (void)d; (void)timeout;
    if (addr != 0x51 || ntx < 1) return MSG_TIMEOUT;
    pcf_xfers_seen++;
    pcf_advance();
    uint8_t r = tx[0], t[7];
    pcf_regs(t);
    bool tw = false;
    for (size_t i = 1; i < ntx; i++, r++) {
        if (r == 0) pcf_write_ctl1(tx[i]);
        else if (r == 1) pcf.ctl2 = tx[i];
        else if (r <= 8) { t[r - 2] = tx[i]; tw = true; }
    }
    if (tw) pcf.epoch = pcf_from_regs(t);     /* the clone keeps its prescaler on a plain time write */
    for (size_t i = 0; i < nrx; i++, r++) {
        if (r == 0) pcf_ctl_reads++;
        rx[i] = r == 0 ? pcf.ctl1 : r == 1 ? pcf.ctl2 : r <= 8 ? t[r - 2] : 0;
    }
    return MSG_OK;
}

/* ---- the rest of the board, stubbed -------------------------------------- */
volatile uint8_t loop_stall_mark;
static uint64_t boot_cyc;
static bool     recovering;
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void     watchdog_record_leave(uint32_t *p) { (void)p; }
bool lcd_blit_busy(void) { return false; }
bool lcd_blit_wait(void) { return true; }
bool display_splash_done(void) { return cyc - boot_cyc >= 2 * F_ILRC; }   /* a 2 s splash */
bool display_bus_idle(void) { return true; }
void display_defer_pass(void) {}
sysinterval_t sleep_pass_ticks(void) { return 0; }
bool sleep_recovering(void) { return recovering; }
bool sn32f2xx_led_committed_dark(void) { return false; }   /* the lights on */
uint32_t last_input_activity_elapsed(void) { return 0; }  /* someone typing */
uint16_t kb_eeconfig_get_rtc_period(void) { return 0; }   /* none stored: RTC_PERIOD_INITIAL */
void rtc_persist_propose(uint16_t p, uint8_t path) { (void)p; (void)path; }
void rtc_persist_task(void) {}
uint32_t timer_read32(void) { return (uint32_t)(cyc * 1000 / F_ILRC); }
systime_t chVTGetSystemTimeX(void) { return (systime_t)(cyc * CH_CFG_ST_FREQUENCY / F_ILRC); }

/* ---- helpers ------------------------------------------------------------- */
static int64_t board_epoch(void) {
    rtc_time_t t;
    if (!rtc_get_time(&t)) return -1;
    struct tm tm = { .tm_sec = t.seconds, .tm_min = t.minutes, .tm_hour = t.hours,
                     .tm_mday = t.day, .tm_mon = t.month - 1, .tm_year = t.year - 1900 };
    return (int64_t)timegm(&tm);
}
static const char *hms(int64_t e) {
    static char b[4][16]; static int i; i = (i + 1) & 3;
    time_t t = (time_t)e; struct tm tm; gmtime_r(&t, &tm);
    snprintf(b[i], sizeof b[i], "%02d:%02d:%02d", tm.tm_hour, tm.tm_min, tm.tm_sec);
    return b[i];
}
static void page4(uint8_t o[28]) { rtc_status_fill(4, o); }
static uint64_t hk_next;
static void boot(void) {
    boot_cyc = cyc;
    rtc_restart = cyc;
    rtcInit();            /* hal_rtc.c -> the LLD's rtc_lld_init (halInit's order) */
    apply_seccntv();
    rtc_init();           /* ak820pro.c:88 */
    apply_seccntv();
    hk_next = cyc;
}
static void pass(void) {
    rtc_fast_task(); apply_seccntv();
    if (cyc >= hk_next) { rtc_task(); apply_seccntv(); hk_next += F_ILRC / 10; }
    rtc_pass_mark();
    advance_to(cyc + PASS_CYC);
}
static void run_s(double s) {
    uint64_t end = cyc + (uint64_t)(s * F_ILRC);
    while (cyc < end) pass();
}
static rtc_time_t true_rtc_time(void) {
    time_t e = (time_t)true_epoch(); struct tm tm; gmtime_r(&e, &tm);
    return (rtc_time_t){ .seconds = (uint8_t)tm.tm_sec, .minutes = (uint8_t)tm.tm_min, .hours = (uint8_t)tm.tm_hour,
                         .day = (uint8_t)tm.tm_mday, .weekday = (uint8_t)tm.tm_wday, .month = (uint8_t)(tm.tm_mon + 1),
                         .year = (uint16_t)(tm.tm_year + 1900) };
}
/* A radio clock sync, as ch582f_ajazz.c:515 makes it: flags 0 (a step) or FRAME. */
static uint8_t host_sync(void) {
    rtc_time_t t = true_rtc_time();
    int16_t off = 0;
    uint8_t st = rtc_set_time_ms(&t, true_ms(), 0, 0x7FFF, &off);
    apply_seccntv();
    printf("  host sync at true %s.%03u: rtc_set_time_ms -> %u (offset before %d ms)\n",
           hms(true_epoch()), true_ms(), st, off);
    return st;
}

static int fails;
#define CHECK(c, ...) do { if (!(c)) { printf("  FAIL: " __VA_ARGS__); printf("\n"); fails++; } else { printf("  ok:   " __VA_ARGS__); printf("\n"); } } while (0)

/* ---- phase A: up, synced, a write run; the reset ------------------------- */
static int phase_a(const char *self, const char *mode) {
    struct tm tb = { .tm_year = 126, .tm_mon = 9, .tm_mday = 31, .tm_hour = 12 };   /* 2026-10-31 12:00:00 UTC */
    T_BASE = (int64_t)timegm(&tb);
    cyc = F_ILRC / 4;                                  /* power on 250 ms into a second */
    pcf = (pcf_t){ .epoch = T_BASE, .ctl1 = 0x08, .next_inc = (int64_t)F_ILRC };   /* right, and in phase */
    printf("[A] boot at true %s.%03u, PCF ctl1 0x%02X\n", hms(true_epoch()), true_ms(), pcf.ctl1);
    boot();
    run_s(120);
    uint8_t o[28]; page4(o);
    int64_t err = board_epoch() - true_epoch();
    printf("[A] after 120 s: true %s board %s err %+" PRId64 " s, acq_state %u (2 = done)\n",
           hms(true_epoch()), hms(board_epoch()), err, o[8]);
    CHECK(err >= -1 && err <= 1, "before the reset the board keeps time (err %+" PRId64 ")", err);

    /* A radio clock sync off USB: an accepted correction, so a write run. */
    host_sync();
    uint64_t t_stop = 0;
    for (int i = 0; i < 200000; i++) {
        pass();
        page4(o);
        if (!t_stop && o[1]) {
            t_stop = cyc;
            printf("[A] write run asserted STOP at true %s.%03u (ps_state %u, PCF ctl1 0x%02X)\n",
                   hms(true_epoch()), true_ms(), o[0], pcf.ctl1);
        }
        if (!strcmp(mode, "stuck") && o[1] && o[0] == 4 /* PS_RELEASE_READ */) break;
        if (!strcmp(mode, "control") && t_stop && o[0] == 0 && !(pcf.ctl1 & PCF_STOP) && cyc - t_stop > 3 * F_ILRC) break;
    }
    page4(o);
    printf("[A] RESET (slider brown-out / watchdog) at true %s.%03u: ps_state %u stop_asserted %u, PCF ctl1 0x%02X, "
           "PCF time %s\n", hms(true_epoch()), true_ms(), o[0], o[1], pcf.ctl1, hms(pcf.epoch));
    pcf_advance();
    cyc += F_ILRC;                                     /* ~1 s of brown-out and boot before rtc_init */
    pcf_advance();
    char a[6][32];
    snprintf(a[0], 32, "%" PRIu64, cyc);       snprintf(a[1], 32, "%" PRId64, T_BASE);
    snprintf(a[2], 32, "%" PRId64, pcf.epoch); snprintf(a[3], 32, "%u", pcf.ctl1);
    snprintf(a[4], 32, "%" PRId64, pcf.next_inc);
    fflush(stdout);
    char *argv2[] = { (char *)self, "after", (char *)mode, a[0], a[1], a[2], a[3], a[4], NULL };
    execv(self, argv2);
    perror("execv");
    return 2;
}

/* ---- phase B: the board after the reset ---------------------------------- */
static int phase_b(const char *mode, char **v) {
    cyc = strtoull(v[0], NULL, 10); T_BASE = strtoll(v[1], NULL, 10);
    pcf.epoch = strtoll(v[2], NULL, 10); pcf.ctl1 = (uint8_t)atoi(v[3]); pcf.next_inc = strtoll(v[4], NULL, 10);
    bool stuck = !strcmp(mode, "stuck");
    int64_t frozen = pcf.epoch;
    printf("[B] boot (all of rtc.c's statics zero) at true %s.%03u; PCF ctl1 0x%02X (STOP %s), PCF time %s\n",
           hms(true_epoch()), true_ms(), pcf.ctl1, (pcf.ctl1 & PCF_STOP) ? "SET" : "clear", hms(pcf.epoch));
    unsigned ctl_reads0 = pcf_ctl_reads;
    boot();
    printf("[B] seeded: board %s (true %s)\n", hms(board_epoch()), hms(true_epoch()));
    uint16_t gen0 = rtc_clock_generation();
    int64_t bmin = INT64_MAX, bmax = INT64_MIN, worst = 0;
    for (int m = 1; m <= 10; m++) {
        for (int s = 0; s < 60; s++) {
            run_s(1.0);
            int64_t b = board_epoch(), e = b - true_epoch();
            if (b < bmin) bmin = b;
            if (b > bmax) bmax = b;
            if ((e < 0 ? -e : e) > (worst < 0 ? -worst : worst)) worst = e;
        }
        uint8_t o[28]; page4(o);
        printf("[B] +%2d min: true %s board %s err %+5" PRId64 " s | snaps so far %u | PCF ctl1 0x%02X time %s | "
               "ps_state %u stop_asserted %u maybe_stopped %u stale %u pending %u acq %u\n",
               m, hms(true_epoch()), hms(board_epoch()), board_epoch() - true_epoch(),
               (unsigned)(uint16_t)(rtc_clock_generation() - gen0), pcf.ctl1, hms(pcf.epoch),
               o[0], o[1], o[7], o[24], o[14], o[8]);
    }
    printf("[B] Control_status_1 reads by the firmware since the reset: %u\n", pcf_ctl_reads - ctl_reads0);
    int64_t err = board_epoch() - true_epoch();
    if (!stuck) {
        CHECK(worst >= -2 && worst <= 2, "control: a reset outside the STOP window keeps time (worst err %+" PRId64 " s)", worst);
        printf(fails ? "RESULT: control FAILED\n" : "RESULT: control passes (no bug without the STOP window)\n");
        return fails ? 1 : 0;
    }
    pcf_advance();
    uint8_t o4[28]; page4(o4);
    uint8_t p1[21]; rtc_status_fill(1, p1);
    CHECK(!(pcf.ctl1 & PCF_STOP), "the boot released STOP (ctl1 0x%02X)", pcf.ctl1);
    CHECK(pcf_ctl_reads - ctl_reads0 >= 1, "the boot read Control_status_1 (%u reads)", pcf_ctl_reads - ctl_reads0);
    CHECK(pcf.epoch > frozen + 590, "the PCF counts again: %s, stopped at %s", hms(pcf.epoch), hms(frozen));
    /* Behind by the time the PCF was stopped, about 1 s of brown-out and boot here. */
    CHECK(worst >= -3 && worst <= 1, "the board keeps time through 10 min, worst err %+" PRId64 " s", worst);
    CHECK((uint16_t)(rtc_clock_generation() - gen0) == 0, "no snap back to the PCF (%u)",
          (unsigned)(uint16_t)(rtc_clock_generation() - gen0));
    CHECK(o4[24] == 1, "the PCF is stale until a host sets the time (stale %u)", o4[24]);
    CHECK((p1[9] & 0x20) != 0, "page 1's flags say the PCF was stopped at boot (0x%02X)", p1[9]);

    /* A short deep sleep (counted <= 5 s): its elapsed time from the PCF. */
    printf("[B] a 4 s deep sleep: rtc_sleep_ok %d\n", rtc_sleep_ok());
    run_s(20);   /* the board 20 s past the snap, so a snap-back shows */
    int64_t before = board_epoch(); uint32_t secs0 = rtc_get_seconds();
    bool prep = rtc_sleep_prepare();
    cyc += 4 * F_ILRC; rtc_restart = cyc;              /* asleep: no ISR served; 4 counted */
    rtc_account_sleepI(4);
    rtc_wake_beginI(4);
    recovering = true;
    rtc_wake_allow();
    uint32_t slept = 0; bool from_pcf = false, got = false;
    for (int i = 0; i < 2000 && (rtc_wake_busy() || !got); i++) {
        pass();
        if (!got && rtc_wake_slept(&slept, &from_pcf)) { got = true; rtc_wake_gauge_taken(); }
    }
    recovering = false;
    printf("[B] sleep: prepare %d; slept %u s (from the PCF: %d) for 4 s asleep; board %s -> %s (true %s); "
           "seconds since boot %u -> %u; acq %u\n", prep, slept, from_pcf, hms(before), hms(board_epoch()),
           hms(true_epoch()), secs0, rtc_get_seconds(), rtc_wake_acq_result());
    err = board_epoch() - true_epoch();
    CHECK(slept >= 3 && slept <= 5, "a 4 s sleep is credited %u s (from the PCF: %d)", slept, from_pcf);
    CHECK(err >= -3 && err <= 1, "the wake keeps the calendar (err %+" PRId64 " s)", err);

    /* A host's correction puts the PCF right and clears stale. */
    printf("[B] a host clock sync arrives (plugged into a host with the agent, or a lock-LED clock frame)\n");
    host_sync();
    run_s(10);
    pcf_advance();
    printf("[B] after the run: PCF ctl1 0x%02X time %s (true %s)\n", pcf.ctl1, hms(pcf.epoch), hms(true_epoch()));
    run_s(300);
    err = board_epoch() - true_epoch();
    page4(o4);
    CHECK(!(pcf.ctl1 & PCF_STOP) && err >= -1 && err <= 1 && o4[24] == 0,
          "a host's sync puts it right: STOP clear, err %+" PRId64 " s five minutes on, stale %u", err, o4[24]);
    printf(fails ? "RESULT: FAIL\n" : "RESULT: PASS (the stopped PCF released at boot; the clock keeps time)\n");
    return fails ? 1 : 0;
}

int main(int argc, char **argv) {
    setenv("TZ", "UTC", 1); tzset();     /* newlib on the board: no TZ */
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (argc >= 8 && !strcmp(argv[1], "after")) return phase_b(argv[2], &argv[3]);
    if (argc >= 2 && (!strcmp(argv[1], "stuck") || !strcmp(argv[1], "control"))) return phase_a(argv[0], argv[1]);
    fprintf(stderr, "usage: %s stuck|control\n", argv[0]);
    return 2;
}
