/* rtc_set_time_ms()'s step, with the SN32's second match landing inside its
 * chSysLock() section (plans/AUDIT-2026-10-31.md, F-025; first written as
 * the audit's verify-020). Before the fix the latched match was served at the
 * unlock, so the board ran (1000 - ms) ms ahead; now the step takes it.
 *
 * Model time: the ILRC runs at exactly F = 33601 Hz, so the board's nominal
 * period (RTC_PERIOD_INITIAL 33600, i.e. 33601 counts) is exact and any error
 * seen is the firmware's. The PCF seeded the board with 12:00:00 at cycle 0;
 * true time at cycle 0 is 12:00:00 + PHASE_MS (the board's phase is arbitrary
 * against true time, as it is before the first host sync after a boot).
 *
 * Each scenario runs in a forked child: rtc.c's state is static, so every
 * scenario gets a fresh boot. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include "hal.h"
#include "rtc.h"
#include "hw_model.h"

#define F 33601ull                 /* ILRC Hz: the board's period, exact */
static int64_t E0;                 /* epoch of 2026-10-31 12:00:00, UTC */
static int64_t phase_ms;           /* true time at cycle 0 = E0 + phase_ms */
static uint32_t lock_cycles;       /* how long the step's locked section lasts */

static int64_t true_ms(uint64_t cyc) { return E0 * 1000 + phase_ms + (int64_t)(cyc * 1000 / F); }

/* The board's time the way rtc.c reads itself (board_ms_now's fraction). */
static bool board_ms(int64_t *out)
{
    rtc_stamp_t s;
    if (!rtc_now(&s)) return false;
    struct tm tm = {0};
    tm.tm_year = s.t.year - 1900; tm.tm_mon = s.t.month - 1; tm.tm_mday = s.t.day;
    tm.tm_hour = s.t.hours; tm.tm_min = s.t.minutes; tm.tm_sec = s.t.seconds;
    int64_t e = (int64_t)timegm(&tm);
    int64_t frac = 1000 - (int64_t)(s.period_active + 1 - s.cnt) * 1000 / (int64_t)(rtc_get_period() + 1);
    *out = e * 1000 + frac;
    return true;
}

static void in_lock_advance(void)
{
    hw_log("chSysLock() #%u: the step's locked section begins (SECCNT %lu of %lu); it lasts %u cycles",
           hw.lock_count, (unsigned long)fake_rtc.SECCNT, (unsigned long)hw.reload, lock_cycles);
    hw_advance(lock_cycles);   /* the time rtcSetTime()'s mktime() takes under the lock */
}

static void boot(void)
{
    setenv("TZ", "UTC", 1);
    tzset();
    hw_reset();
    hw.pcf_year = 26; hw.pcf_mon = 10; hw.pcf_day = 31; hw.pcf_wday = 6;
    hw.pcf_hour = 12; hw.pcf_min = 0; hw.pcf_sec = 0;
    rtc_lld_init();
    rtc_init();                /* P_nom 33600, the callback, the PCF seed */
}

/* One step. `before_match`: cycles from the moment the step's lock begins to
 * the next match (0 = the match is the first cycle inside the lock). `ms` is
 * computed from the model's true time, as a perfect host would send it.
 * Returns the board's error (board - true) right after the step and at the
 * next two ticks; prints when verbose. */
typedef struct { int st; int64_t err_after, err_tick1, err_tick2; uint64_t tick1_cyc, tick2_cyc; int16_t off; } result_t;

static result_t scenario(int64_t phase, uint32_t before_match, uint32_t lockc, uint8_t flags, bool verbose)
{
    result_t r = {0};
    phase_ms = phase; lock_cycles = lockc;
    boot();
    hw.verbose = verbose;
    /* Run to 3 s, then up to `before_match` cycles before the 4th match. */
    uint64_t target = 3 * F - before_match;
    hw_advance(target - hw.now);
    int64_t tm_ = true_ms(hw.now);
    time_t ts = (time_t)(tm_ / 1000);
    uint16_t ms = (uint16_t)(tm_ % 1000);
    struct tm tt; gmtime_r(&ts, &tt);
    rtc_time_t t = { .seconds = tt.tm_sec, .minutes = tt.tm_min, .hours = tt.tm_hour, .day = tt.tm_mday,
                     .weekday = tt.tm_wday, .month = tt.tm_mon + 1, .year = tt.tm_year + 1900 };
    if (verbose) printf("  host: true time at receipt %02d:%02d:%02d.%03u, cycle %llu; SECCNT %lu of %lu\n",
                        tt.tm_hour, tt.tm_min, tt.tm_sec, ms, (unsigned long long)hw.now,
                        (unsigned long)fake_rtc.SECCNT, (unsigned long)hw.reload);
    if (lockc) hw.lock_hook = in_lock_advance;
    uint32_t isr0 = hw.isr_runs;
    r.st = rtc_set_time_ms(&t, ms, flags, 0x7FFF, &r.off);
    hw.lock_hook = NULL;
    int64_t b;
    if (board_ms(&b)) r.err_after = b - true_ms(hw.now);
    if (verbose) printf("  rtc_set_time_ms -> %d (0 = STEPPED), offset before %d ms; ISRs during the call: %u\n",
                        r.st, r.off, hw.isr_runs - isr0);
    /* The next two ticks. */
    for (int k = 0; k < 2; k++) {
        uint32_t n0 = hw.isr_runs;
        while (hw.isr_runs == n0) hw_advance(1);
        int64_t bt;
        board_ms(&bt);
        int64_t e = bt - true_ms(hw.now);
        if (k == 0) { r.err_tick1 = e; r.tick1_cyc = hw.now; } else { r.err_tick2 = e; r.tick2_cyc = hw.now; }
    }
    if (verbose) {
        printf("  board - true: right after the step %+lld ms; at the next tick %+lld ms (cycle %llu); at the one after %+lld ms (cycle %llu)\n",
               (long long)r.err_after, (long long)r.err_tick1, (unsigned long long)r.tick1_cyc,
               (long long)r.err_tick2, (unsigned long long)r.tick2_cyc);
        rtc_time_t now; rtc_get_time(&now);
        printf("  the calendar now reads %02u:%02u:%02u at true %lld.%03lld s past 12:00:00\n", now.hours, now.minutes,
               now.seconds, (long long)((true_ms(hw.now) - E0 * 1000) / 1000), (long long)((true_ms(hw.now) - E0 * 1000) % 1000));
    }
    return r;
}

static int run_child(int64_t phase, uint32_t before, uint32_t lockc, uint8_t flags, bool verbose, result_t *out)
{
    int fd[2];
    if (pipe(fd)) return -1;
    fflush(stdout);
    pid_t p = fork();
    if (p == 0) {
        close(fd[0]);
        result_t r = scenario(phase, before, lockc, flags, verbose);
        fflush(stdout);
        if (write(fd[1], &r, sizeof r) != sizeof r) _exit(3);
        _exit(0);
    }
    close(fd[1]);
    ssize_t n = read(fd[0], out, sizeof *out);
    close(fd[0]);
    int status = 0;
    waitpid(p, &status, 0);
    if (n != sizeof *out || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        printf("  child failed (status 0x%x)\n", status);
        return -1;
    }
    return 0;
}

static int fails;
#define CHECK(c, ...) do { if (!(c)) { printf("FAIL: " __VA_ARGS__); printf("\n"); fails++; } else { printf("ok:   " __VA_ARGS__); printf("\n"); } } while (0)

int main(void)
{
    setenv("TZ", "UTC", 1);
    tzset();
    struct tm e0 = { .tm_year = 126, .tm_mon = 9, .tm_mday = 31, .tm_hour = 12 };
    E0 = (int64_t)timegm(&e0);
    result_t r;

    printf("A. Control: the step's lock (3 cycles, ~90 us) begins 2000 cycles before the match.\n");
    run_child(400, 2000, 3, 0, true, &r);
    CHECK(r.st == RTC_SET_STEPPED && llabs(r.err_after) <= 1 && llabs(r.err_tick1) <= 1 && llabs(r.err_tick2) <= 1,
          "A: stepped, the board within 1 ms of true time (after %+lld, tick %+lld, tick %+lld)",
          (long long)r.err_after, (long long)r.err_tick1, (long long)r.err_tick2);

    printf("\nB. A host's first sync after boot (flags 0), its lock beginning 1 cycle before the match.\n");
    run_child(400, 1, 3, 0, true, &r);
    CHECK(r.st == RTC_SET_STEPPED, "B: the firmware reports RTC_SET_STEPPED");
    CHECK(llabs(r.err_tick2) <= 1, "B: board within 1 ms of true time two ticks later (it is %+lld ms)", (long long)r.err_tick2);

    printf("\nC. The wake's acquisition flags (FORCE_STEP|SKIP_PCF|INTERNAL), the same moment.\n");
    run_child(400, 1, 3, RTC_SETF_FORCE_STEP | RTC_SETF_SKIP_PCF | RTC_SETF_INTERNAL, true, &r);
    CHECK(llabs(r.err_tick2) <= 1, "C: board within 1 ms of true time two ticks later (it is %+lld ms)", (long long)r.err_tick2);

    printf("\nD. The R < 20 ms branch: true ms at receipt 990.\n");
    run_child(-10, 1, 3, 0, true, &r);
    CHECK(llabs(r.err_tick2) <= 1, "D: board within 1 ms of true time two ticks later (it is %+lld ms)", (long long)r.err_tick2);

    printf("\nE. The window: the step's lock lasts 3 cycles; where the match falls against it.\n");
    printf("   before_match  err after 2 ticks (ms)\n");
    int bad = 0, tot = 0;
    for (uint32_t before = 0; before <= 8; before++) {
        run_child(400, before, 3, 0, false, &r);
        printf("   %12u  %+lld%s\n", before, (long long)r.err_tick2, llabs(r.err_tick2) > 1 ? "   <- wrong" : "");
        tot++; if (llabs(r.err_tick2) > 1) bad++;
    }
    printf("   (0: the match falls on the cycle before the lock and is served normally; 1..3: it falls inside\n"
           "    the 3-cycle lock, before the SECCNTV write; 4+: the write restarts the counter before it comes)\n");
    printf("   %d of %d positions wrong\n", bad, tot);
    CHECK(bad == 0, "E: no position of the match against the lock leaves the board off");

    printf("\nF. The error against the host's ms (the lock's start 1 cycle before the match, 3 cycles long).\n");
    printf("   true ms   err (ms)   predicted 1000 - ms (or 2000 - ms if R < 20)\n");
    int64_t phases[] = {0, 100, 250, 500, 750, 900, 970, 985, 995};
    for (unsigned i = 0; i < sizeof phases / sizeof *phases; i++) {
        run_child(phases[i], 1, 3, 0, false, &r);
        int64_t msr = ((phases[i] % 1000) + 1000 - 1) % 1000;   /* true ms at receipt: one cycle before the board's boundary */
        int64_t pred = (1000 - msr) < 20 ? 2000 - msr : 1000 - msr;
        printf("   %7lld   %+8lld   %+lld (before the fix)\n", (long long)msr, (long long)r.err_tick2, (long long)pred);
        if (llabs(r.err_tick2) > 1) { printf("FAIL: F: %lld ms at receipt ms %lld\n", (long long)r.err_tick2, (long long)msr); fails++; }
    }

    printf("\nRESULT: %s (%d failed checks)\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
