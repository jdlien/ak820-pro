/* The battery gauge's ratchet never raises the level on battery (the 10-31
 * audit, F-021; first written as its verify-047). Its run (below_run,
 * below_best) survived c5_forget(), so after a deep sleep's debit, or a long
 * gap in the radio's 5C reports with the count running, the first completed
 * run could move the level UP: before the fix 108 of 203 gap cases rose.
 *
 * Compiles the board's battery.c VERBATIM (run.sh copies it beside
 * scripts/battery_sim's stubs), #included here for white-box access to
 * below_run, below_best and level, plus power.c as its own translation unit.
 * The world below is a trimmed copy of scripts/battery_sim/sim.c's.
 *
 * Each case runs in a forked child, so battery.c's file statics start from
 * boot every time. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>

#include "battery.c"   /* the firmware's, copied by run.sh */

struct fake_adc fake_adc;

/* --- The world (after sim.c) ------------------------------------------------ */
static uint32_t now_ms;
static int      vdd_mv = 3900;            /* on the pack: the buck-boost's ~3.90 V */
static bool     chrg_low;
static int      c5w = 0xFF;               /* what the module reports; 0xFF silent */
static uint8_t  module_level = 0xFF;
static uint16_t reports;
static uint32_t last_recv;
static bool     seen, rx_stale;           /* rx_stale: ch582_sleep_wake()'s battery_stale */
static uint8_t  scale = 255;

uint32_t timer_read32(void) { return now_ms; }
uint32_t timer_elapsed32(uint32_t last) { return now_ms - last; }
uint32_t last_input_activity_elapsed(void) { return 0; }   /* typing: the ladder stays at Full */
bool     gpio_read_pin(int pin) { return pin == CHARGE_CHRG_PIN ? !chrg_low : true; }
bool     rgb_matrix_is_enabled(void) { return true; }
uint8_t  ch582_get_battery(void) { return module_level; }
/* As ch582f_ajazz.c: UINT32_MAX if never seen, or stale since a deep sleep's wake. */
uint32_t ch582_battery_age_ms(void) { return (!seen || rx_stale) ? UINT32_MAX : now_ms - last_recv; }
uint16_t ch582_battery_reports(void) { return reports; }
bool     ch582_is_usb(void) { return false; }
bool     ch582_is_connected(void) { return true; }
void     display_set_alert(const char *m) { (void)m; }
void     display_set_param_status(const char *s) { (void)s; }
bool     display_message_recent(uint32_t ms) { (void)ms; return false; }
bool     display_band_busy(void) { return false; }
bool     display_debug_active(void) { return false; }
bool     display_panel_lit_for_owner(void) { return false; }
rgb_t    hsv_to_rgb(hsv_t c) { rgb_t r = {c.v, c.v, c.v}; return r; }
static uint8_t power_mode_p1;
bool kb_eeconfig_get_power_mode(uint8_t *m) {
    if (power_mode_p1 == 0) return false;
    *m = (uint8_t)(power_mode_p1 - 1u);
    return true;
}
void kb_eeconfig_set_power_mode(uint8_t m) { power_mode_p1 = (uint8_t)(m + 1u); }
static uint8_t bkl_cap = 0xFF;
void     display_set_backlight_cap(uint8_t c) { bkl_cap = c; }
uint8_t  display_backlight_effective(void) { return bkl_cap < 10 ? bkl_cap : 10; }
uint8_t  display_backlight_duty(void) { return 9; }
static uint8_t rgb_mode = 2;
uint8_t  rgb_matrix_get_mode(void) { return rgb_mode; }
void     rgb_matrix_mode_noeeprom(uint8_t m) { rgb_mode = m; }
void     rgb_matrix_reinit_effect(void) {}
bool     battery_usb_configured(void) { return false; }
static uint32_t drive_sum = 81u * 3u * 255u;   /* full white, as sim.c */
static uint32_t drive_last_ms;
uint64_t sn32f2xx_led_drive_take(uint32_t now, uint32_t *lit_ms, uint64_t rgb_ms[3]) {
    uint32_t dt  = now - drive_last_ms;
    uint32_t sum = scale ? (drive_sum * (scale + 1u)) >> 8 : 0u;
    drive_last_ms = now;
    if (lit_ms) *lit_ms = sum ? dt : 0u;
    if (rgb_ms) {
        uint64_t third = (uint64_t)(sum / 3u) * dt;
        rgb_ms[1] = rgb_ms[2] = third;
        rgb_ms[0] = (uint64_t)sum * dt - 2u * third;
    }
    return (uint64_t)sum * dt;
}
uint32_t sn32f2xx_led_load(void) { return scale ? 81u * 3u * 255u / 2u : 0u; }
void     sn32f2xx_set_power_scale(uint8_t s) { scale = s; }
static uint8_t saved_p1;
static int     saved_writes;
bool kb_eeconfig_get_batt_level(uint16_t *pm) {
    if (saved_p1 == 0 || saved_p1 > 201) return false;
    *pm = (uint16_t)((saved_p1 - 1u) * 5u);
    return true;
}
void kb_eeconfig_set_batt_level(uint16_t pm) {
    if (pm > 1000u) return;
    uint8_t p1 = (uint8_t)(pm / 5u + 1u);
    if (p1 != saved_p1) saved_writes++;
    saved_p1 = p1;
}

/* One 5C frame as the CH582F driver hands it over. */
static void deliver(uint8_t v) {
    module_level = v;
    reports++;
    last_recv = now_ms;
    seen      = true;
    rx_stale  = false;
    battery_5c_report(v);
}

/* The level watch: on the pack with no re-seat owed it must never rise. */
static uint16_t w_prev = LEVEL_UNKNOWN;
static int      w_rises, w_rise_max;
static uint16_t w_rise_from, w_rise_to;
static uint32_t w_rise_at;
static bool     watching;
static bool     trace_on;

static void tick(void) {
    now_ms += 100;
    fake_adc.ADB = (uint32_t)((2000u * 4096u + (unsigned)vdd_mv / 2u) / (unsigned)vdd_mv);
    if (c5w <= 100 && now_ms % 2500u == 0) deliver((uint8_t)c5w);   /* ~2.6 s on the board */
    battery_task();
    if (watching && supply == BATTERY_SUPPLY_BATTERY && !reseat && level != LEVEL_UNKNOWN &&
        w_prev != LEVEL_UNKNOWN && level > w_prev) {
        if (w_rises == 0) { w_rise_from = w_prev; w_rise_to = level; w_rise_at = now_ms; }
        w_rises++;
        if ((int)(level - w_prev) > w_rise_max) w_rise_max = (int)(level - w_prev);
    }
    if (trace_on && level != w_prev)
        printf("    TRACE t=%.1fs level %u -> %u (%u%% -> %u%%) est=%u below_run=%u below_best=%u\n", now_ms / 1000.0, w_prev,
               level, (w_prev + 5u) / 10u, (level + 5u) / 10u, battery_5c_x100(), below_run, below_best);
    w_prev = level;
}
static void run_s(uint32_t s) { for (uint32_t i = 0; i < s * 10u; i++) tick(); }

/* Up to the next fresh estimate (a report); returns false after max_s. */
static bool next_report(uint32_t max_s) {
    uint16_t r0 = reports;
    for (uint32_t i = 0; i < max_s * 10u; i++) {
        tick();
        if (reports != r0) return true;
    }
    return false;
}

/* Boot on the pack and walk the module's report down so the voltage leads
 * the count: the ratchet runs. The level is watched from the boot on: the
 * walk itself (the awake ratchet, no gap) must never raise it -- the control.
 * Then stop at the first report after which the run is open at `want_run`
 * with the level above the band. */
static int setup_rises;
static bool reach_open_run(uint8_t want_run) {
    vdd_mv = 3900; chrg_low = false;
    c5w = 62;
    run_s(30);
    if (supply != BATTERY_SUPPLY_BATTERY || level == LEVEL_UNKNOWN) return false;
    w_prev = level; w_rises = 0; w_rise_max = 0; watching = true;
    /* The voltage falls one count every 8 reports (~20 s/count, ~9 mV): far
     * faster than the count's ~19 pm/h, so the level sits above the band and
     * the ratchet steps it down every six estimates. */
    for (int n = 0; n < 2000; n++) {
        if (n % 8 == 7 && c5w > 40) c5w--;
        if (!next_report(5)) return false;
        if (c5w <= 56 && below_run == want_run) {
            uint16_t m = battery_5c_x100();
            if (m != C5_EST_NONE && (int32_t)level > band_upper(c5_to_mv(m))) {
                setup_rises = w_rises;
                return true;
            }
        }
    }
    return false;
}

typedef struct {
    int      kind;          /* 0 sleep, 1 radio gap, 2 control: no gap, the walk goes on */
    uint8_t  want_run;      /* below_run at the sleep's entry, 1..5 */
    uint32_t gap_s;         /* slept seconds, or the radio's silence */
    int      post_drop;     /* the module's report after the gap: counts below the PRE-GAP ESTIMATE, rounded */
    int      verbose;
} case_t;

static int run_case(const case_t *c) {
    battery_init();
    if (!reach_open_run(c->want_run)) {
        printf("  setup failed (run %u)\n", c->want_run);
        return 2;
    }
    uint16_t m0 = battery_5c_x100();
    uint16_t pre_level = level, pre_best = below_best;
    uint8_t  pre_run = below_run;
    int32_t  pre_up = band_upper(c5_to_mv(m0));
    int      c5_before = (m0 + 50) / 100;   /* the voltage before the gap, as the estimate had it */

    w_prev = level; w_rises = 0; w_rise_max = 0; watching = true;
    if (c->kind == 2) {
        /* The control: the same walk, awake, no gap: 120 s more of it. */
        for (int n = 0; n < 48; n++) {
            if (n % 8 == 7 && c5w > 40) c5w--;
            next_report(5);
        }
        uint16_t m1 = battery_5c_x100();
        printf("  ctrl  run=%u          | pre: lvl=%u best=%u run=%u upper=%d est=%u | post: est=%u upper=%d lvl=%u | rises=%d (setup walk rises=%d)\n",
               c->want_run, pre_level, pre_best, pre_run, pre_up, m0, m1, band_upper(c5_to_mv(m1)), level, w_rises, setup_rises);
        return (w_rises || setup_rises) ? 1 : 0;
    }
    if (c->kind == 0) {
        /* sleep.c: battery_sleep_enter() before the lock; the timer stands
         * still; at the wake battery_sleep_wake() and ch582_sleep_wake()
         * (battery_stale, the poll held); the gauge step accounts the slept
         * time within ~1-3.5 s, before the first post-wake estimate (which
         * needs C5_MIN_EST = 5 reports). */
        battery_sleep_enter();
        battery_sleep_wake();
        rx_stale = true;
        c5w = 0xFF;
        for (int i = 0; i < 20; i++) tick();      /* 2 s of recovery, no reports */
        battery_sleep_account(c->gap_s * 1000u);
    } else {
        /* The module falls silent: the ring goes stale after 20 s and is
         * forgotten; the count runs with no bound. */
        c5w = 0xFF;
        run_s(c->gap_s);
    }
    trace_on = getenv("TRACE") != NULL;
    uint16_t after_gap = level;
    uint8_t  run_after_gap = below_run;
    uint16_t best_after_gap = below_best;
    c5w = c5_before - c->post_drop;
    run_s(120);   /* ~48 reports: the stale run completes, then fresh runs */
    uint16_t m1 = battery_5c_x100();
    int32_t  post_up = m1 != C5_EST_NONE ? band_upper(c5_to_mv(m1)) : -1;

    printf("  %-5s run=%u gap=%6us drop=%d | pre: lvl=%u best=%u run=%u upper=%d est=%u | after gap: lvl=%u run=%u best=%u"
           " | post: c5=%d upper=%d lvl=%u | rises=%d",
           c->kind ? "radio" : "sleep", c->want_run, c->gap_s, c->post_drop, pre_level, pre_best, pre_run, pre_up,
           m0, after_gap, run_after_gap, best_after_gap, c5w, post_up, level, w_rises);
    if (w_rises) printf(" FIRST %u->%u at t=%.1fs (%u%%->%u%%) max+%d", w_rise_from, w_rise_to, w_rise_at / 1000.0,
                        (w_rise_from + 5u) / 10u, (w_rise_to + 5u) / 10u, w_rise_max);
    printf("\n");
    if (setup_rises) printf("  !! the setup walk itself rose %d times\n", setup_rises);
    return w_rises ? 1 : 0;
}

static int run_one(case_t c) {
    fflush(stdout);
    pid_t p = fork();
    if (p == 0) { int rc0 = run_case(&c); fflush(stdout); _exit(rc0); }
    int st; waitpid(p, &st, 0);
    return WIFEXITED(st) ? WEXITSTATUS(st) : 99;
}

int main(int argc, char **argv) {
    int verbose = argc > 1;
    if (argc > 4) {   /* one case: kind run gap_s drop */
        case_t c = {atoi(argv[1]), (uint8_t)atoi(argv[2]), (uint32_t)atoi(argv[3]), atoi(argv[4]), 1};
        return run_case(&c);
    }
    static const uint32_t sleeps[] = {3600u, 4u * 3600u, 44461u, 86400u + 12600u /* 27.5 h, the backstop */};
    static const int      drops[]  = {0, 1, 2, 3, 4, 6, 8};
    int rose = 0, clean = 0, setup = 0, ctrl_rose = 0;
    printf("== control: the same walk, awake, no gap (the ratchet alone must never rise) ==\n");
    for (uint8_t r = 1; r <= 5; r++) {
        case_t c = {2, r, 0, 0, verbose};
        int rc = run_one(c);
        if (rc == 1) ctrl_rose++; else if (rc != 0) setup++;
    }
    printf("== deep sleep: level above the band, the ratchet's run open at the entry ==\n");
    for (unsigned si = 0; si < sizeof sleeps / sizeof sleeps[0]; si++)
        for (unsigned di = 0; di < sizeof drops / sizeof drops[0]; di++)
            for (uint8_t r = 1; r <= 5; r++) {
                case_t c = {0, r, sleeps[si], drops[di], verbose};
                int rc = run_one(c);
                if (rc == 1) rose++; else if (rc == 0) clean++; else setup++;
            }
    printf("== radio gap (the module silent, awake, the count running) ==\n");
    static const uint32_t gaps[] = {600u, 1800u, 3840u};
    for (unsigned gi = 0; gi < sizeof gaps / sizeof gaps[0]; gi++)
        for (unsigned di = 0; di < sizeof drops / sizeof drops[0]; di++)
            for (uint8_t r = 1; r <= 5; r += 2) {
                case_t c = {1, r, gaps[gi], drops[di], verbose};
                int rc = run_one(c);
                if (rc == 1) rose++; else if (rc == 0) clean++; else setup++;
            }
    printf("SUMMARY: control rises %d; %d gap cases with the level rising on battery, %d clean, %d setup/abnormal\n",
           ctrl_rose, rose, clean, setup);
    return rose ? 1 : 0;
}
