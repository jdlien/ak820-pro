/* sleep_task()'s 64-bit timer reads per main-loop pass
 * (plans/AUDIT-2026-10-31.md, F-027; first written as the audit's verify-011):
 * recovery_task() no longer reads the timer when no wake is being watched.
 * The original description follows. */
/* verify-011: does the real sleep_task() (sleep.c, every build) pay for
 * timer_read32() -- QMK's real chibios timer.c, whose TIME_I2MS is a 64-bit
 * multiply and a 64-bit software divide on the M0 -- on every main-loop pass
 * even when no wake's recovery has ever run?
 *
 * Compiled with the real sleep.c, power.c, platforms/chibios/timer.c and
 * platforms/timer.c. last_input_activity_elapsed() below is quantum/
 * keyboard.c:159-161's body (sync_timer_elapsed32 is timer_elapsed32 without
 * SPLIT_KEYBOARD, quantum/sync_timer.h:49). */
#include <stdio.h>
#include <stdlib.h>
#include "hal.h"
#include "quantum.h"
#include "power.h"
#include "sleep.h"

extern bool host_on_battery;
extern unsigned host_n_blockers_calls;

static uint32_t last_input_modification_time = 0;
uint32_t last_input_activity_elapsed(void) { return timer_elapsed32(last_input_modification_time); }

#define PASS_TICKS 675u   /* ~3.6 ms a pass (passes/s ~275, BATTERY-GAUGE-REFINE-PLAN.md:1320) at 187.5 kHz */

static void advance_pass(bool host_frames) {
    host_ticks += PASS_TICKS;
    if (host_frames) host_usb.FRMNO = (host_usb.FRMNO + 4u) & 0x7FFu;   /* a SOF a ms: ~3-4 a pass */
}

typedef struct { unsigned i2ms, locks; uint64_t iters; } count_t;
static int fails;

static count_t run(const char *name, bool battery, bool frames, power_mode_t mode, unsigned passes, unsigned expect) {
    host_on_battery = battery;
    power_set_mode(mode);
    unsigned b0 = host_n_blockers_calls;
    count_t c = {0, 0, 0};
    for (unsigned p = 0; p < passes; p++) {
        advance_pass(frames);
        last_input_modification_time = timer_read32();   /* typing: the ladder never wants a sleep (the harness's read, not counted) */
        unsigned i0 = host_n_i2ms, l0 = host_n_lock; uint64_t it0 = host_div_iters;
        sleep_task();
        c.i2ms  += host_n_i2ms - i0;
        c.locks += host_n_lock - l0;
        c.iters += host_div_iters - it0;
    }
    double per = (double)c.i2ms / passes;
    printf("%-58s %5.2f timer_read32/pass (64-bit mul+div each), %5.2f locks/pass, %4.1f divide iterations/read  %s\n",
           name, per, (double)c.locks / passes, c.i2ms ? (double)c.iters / c.i2ms : 0.0,
           (per == (double)expect && host_n_blockers_calls == b0 && !sleep_recovering()) ? "[ok]" : "[FAIL]");
    if (!(per == (double)expect && host_n_blockers_calls == b0 && !sleep_recovering())) fails++;
    return c;
}

int main(void) {
    timer_init();
    power_init();                         /* kb_eeconfig empty: POWER_MODE_DEFAULT, Balanced */
    host_usb.FRMNO = 0;
    /* Warm up to an hour of uptime, so the divide's dividend is realistic. */
    /* In 0.2 s steps: the 16-bit counter must be read at least once a wrap (0.35 s), which the firmware's update_fn VT guarantees. */
    for (uint32_t s = 0; s < 18000u; s++) { host_ticks += 37500u; (void)timer_read32(); }
    host_n_i2ms = 0; host_n_lock = 0; host_div_iters = 0;

    printf("sleep_recovering() = %d (no deep sleep since boot: rc_active false)\n\n", sleep_recovering());
    /* Before the fix each was one read more: recovery_task()'s, with no wake
     * since boot (F-027). What is left: usb_watch()'s while frames move, and
     * power_sleep_wanted()'s on battery outside Always on. */
    run("USB, host present (FRMNO moving), Always on",                 false, true,  POWER_MODE_FULL,    1000, 1);
    run("USB, host present (FRMNO moving), Balanced (the default)",    false, true,  POWER_MODE_NORMAL,  1000, 1);
    run("USB, host absent/suspended (FRMNO still), Balanced",          false, false, POWER_MODE_NORMAL,  1000, 0);
    run("battery (no host), Always on",                                true,  false, POWER_MODE_FULL,    1000, 0);
    run("battery (no host), Balanced (the default)",                   true,  false, POWER_MODE_NORMAL,  1000, 1);
    run("battery (no host), Power saver",                              true,  false, POWER_MODE_SAVER,   1000, 1);
    run("battery (no host), Lights out",                               true,  false, POWER_MODE_MINIMAL, 1000, 1);

    /* The divide's length grows with uptime: the quotient is ms since boot
     * (under 2^32 ticks, ~6.4 h, then timer.c rebases). */
    printf("\n__udivmoddi4 iterations per timer_read32 by uptime (each ~9-18 cycles on the M0):\n");
    uint32_t ups[] = {60u, 600u, 3600u, 6u * 3600u};
    for (unsigned k = 0; k < 4; k++) {
        uint64_t ticks = (uint64_t)ups[k] * 187500u;
        uint64_t num = ticks * 1000u + 187499u;
        int it = host_clz64(187500u) - host_clz64(num);
        printf("  uptime %6u s: dividend 2^%.1f, %d iterations\n", ups[k], 63.0 - host_clz64(num), it);
    }
    printf("RESULT: %s\n", fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}
