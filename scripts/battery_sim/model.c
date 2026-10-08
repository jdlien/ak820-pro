/* Phase 1b, B2: the charging model's scenarios (plans/BATTERY-GAUGE-REFINE-PLAN.md,
 * "B2. Simulator", after B3). Included into sim.c when battery.h says log v5,
 * so it shares the simulated world and the helpers. Cases marked SYNTHETIC
 * are constructed inputs and say so in their output; the replays use recorded
 * data through the replay adapter.
 *
 * The parameters are battery_tail.h's (BATT_*: K_CC, L_KNEE, T_TAIL) and the
 * model's constants battery.h's (BATTERY_*), so every expectation below moves
 * with the values the firmware ships. tail_fw_grid.py builds this at every
 * point of B1's grid (m_overrun) and runs the cases the plan names at round 3's
 * set; mutants.py checks each of the plan's mutants is caught. */
#include <math.h>
#include "battery_tail.h"

enum { ST_NONE = 0, ST_UNKNOWN, ST_FROM_FLAT, ST_MODEL, ST_LOST, ST_FULL };
#define K   ((int)BATT_K_CC_PM_PER_H)
#define LK  ((int)BATT_L_KNEE_PM)
#define TT  ((uint32_t)BATT_T_TAIL_S)

static void synthetic(const char *what) { printf("  [synthetic] %s\n", what); }

/* The curve inverted: the lowest pack mV whose level is >= pm, as a fractional
 * 5C count (5C = 114.22 V - 361.04). Above the curve's top (900 at 4036 mV)
 * there is nothing below the clamp. */
static double c5_for_pm(int pm) {
    int lo = 3300, hi = 4036;
    while (lo < hi) {
        int mid = (lo + hi) / 2;
        if ((int)battery_curve_pm((uint16_t)mid) >= pm) hi = mid; else lo = mid + 1;
    }
    return 114.22 * lo / 1000.0 - 361.04;
}

/* U now, as the firmware computes it: the curve at a fresh below-clamp
 * estimate; -1 when there is no voltage bound (stale, or at the clamp). */
static int u_now(void) {
    uint16_t e = battery_5c_x100();
    if (e == 0xFFFFu || e >= 9950u) return -1;
    if (e < 50u) return 0;
    uint16_t mv = (uint16_t)((((uint32_t)e + 36104u) * 1000u + 5711u) / 11422u);
    return battery_curve_pm(mv);
}

/* Reports that make U follow a target, by error diffusion between adjacent
 * counts; the 64-report trimmed mean then sits within ~a tenth of a count. */
static int    (*u_target)(void);
static double u_err;
static int u_follow(void) {
    int t = u_target();
    if (t > 100000) return 101;   /* "no report" */
    if (t >= 2000) return 100;    /* the clamp */
    double want = c5_for_pm(t) + u_err;
    int v = (int)floor(want + 0.5);
    u_err = want - v;
    return v < 0 ? 0 : v > 99 ? 99 : v;
}
static int u_delta;   /* the gap the following targets keep, pm */
static int m_now(void) {
    uint16_t m = battery_model_pm();
    return m == 0xFFFFu ? (int)battery_level_permille() : (int)m;
}
/* U = M - delta, led by the estimate's ~80 s lag (M rises ~4 pm in 80 s at K_CC). */
static int tgt_m_minus(void) { return m_now() + (K * 80) / 3600 - u_delta; }
static int tgt_clamp(void) { return 5000; }

static int tgt_fixed_pm;
static int tgt_fixed(void) { return tgt_fixed_pm; }

/* Per-second watch of the display rules. */
static uint16_t pw_level;
static int pw_fall, pw_rise_big, pw_over_cap, pw_ceiling, pw_secs;
static void pw_reset(void) { pw_level = battery_level_permille(); pw_fall = pw_rise_big = pw_over_cap = pw_ceiling = pw_secs = 0; }
static void run_pw(uint32_t s) {
    for (uint32_t i = 0; i < s; i++) {
        int u0 = u_now();
        run_s(1);
        int u1 = u_now();
        uint16_t l = battery_level_permille();
        if (l != 0xFFFFu && pw_level != 0xFFFFu) {
            if (l < pw_level) pw_fall++;
            if (l > pw_level + 1u) pw_rise_big++;
            int u = u0 > u1 ? u0 : u1;   /* the firmware ticked somewhere in this second */
            if (l > pw_level && u0 >= 0 && u1 >= 0 && (int)l > u) pw_ceiling++;
        }
        if (l != 0xFFFFu && l > BATTERY_MODEL_CAP && battery_chg_state() != ST_FULL) pw_over_cap++;
        pw_level = l;
        pw_secs++;
    }
}

/* On the pack at about `l0`, then plugged in and charging with `src` driving
 * the reports, until a MODEL session opens. Returns the level it opened at. */
static uint16_t model_from(int l0, int (*src)(void)) {
    c5_src = NULL; c5 = (uint8_t)lround(c5_for_pm(l0)); vdd_mv = 3900; chrg_low = false;
    run_s(40);
    vdd_mv = 4193; chrg_low = true; c5_src = src; u_err = 0;
    for (int i = 0; i < 120 && battery_chg_state() != ST_MODEL; i++) run_s(1);
    CHECK(battery_chg_state() == ST_MODEL, "a MODEL session opened: state %u", battery_chg_state());
    return battery_level_permille();
}

/* --- Starts ------------------------------------------------------------------ */

/* FROM-FLAT's boundary through real reports: the first estimate averages five
 * whole counts untrimmed (resolution 0.20), so 10,10,10,10,10 is 10.00 and
 * 10,10,10,10,11 is 10.20. The 10.00/10.01 edge is the helper's. */
static int flat_seq[5], flat_i;
static int flat_src(void) { return flat_i < 5 ? flat_seq[flat_i++] : 40; }
static void boot_flat(int last) {
    synthetic("a boot on USB, charging, first five reports 10,10,10,10,last");
    for (int i = 0; i < 4; i++) flat_seq[i] = 10;
    flat_seq[4] = last; flat_i = 0;
    vdd_mv = 4193; chrg_low = true;
    run_s(2);
    c5_src = flat_src;
    run_s(75);
}
static void m_flat_boundary(void) {
    CHECK(battery_first_estimate_is_flat(1000), "10.00 is flat");
    CHECK(!battery_first_estimate_is_flat(1001), "10.01 is not");
    CHECK(!battery_first_estimate_is_flat(0xFFFF), "no estimate is not");
    boot_flat(10);
    CHECK(battery_chg_state() == ST_FROM_FLAT && battery_level_permille() <= 2, "10.00 -> FROM-FLAT at 0: %u %u",
          battery_chg_state(), battery_level_permille());
}
static void m_flat_boundary_above(void) {
    boot_flat(11);
    CHECK(battery_chg_state() == ST_UNKNOWN && battery_level_permille() == 0xFFFF, "10.20 -> UNKNOWN-CHG: %u %u",
          battery_chg_state(), battery_level_permille());
}

/* A boot on USB at the clamp, nothing known: "Charge" throughout, 1000 at FULL. */
static void m_unknown_start(void) {
    synthetic("a boot on USB at the clamp, charging, nothing saved");
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(30);
    CHECK(battery_level_permille() == 0xFFFF, "before the session: unknown (\"Charge\")");
    run_s(2 * 3600);
    CHECK(battery_chg_state() == ST_UNKNOWN && battery_level_permille() == 0xFFFF, "UNKNOWN-CHG for 2 h: %u %u",
          battery_chg_state(), battery_level_permille());
    chrg_low = false; vdd_mv = 4470;
    run_s(30);
    CHECK(battery_level_permille() == 1000 && battery_chg_state() == ST_FULL, "1000 at FULL: %u",
          battery_level_permille());
}

/* --- The model's shape -------------------------------------------------------- */

/* Below the knee: L0 = L_KNEE - K_CC - 50, U kept above M; an hour adds K_CC. */
static void m_partial_below_knee(void) {
    synthetic("L0 = L_KNEE - K_CC - 50, 5C keeping U ~100 pm above M");
    u_delta = -100;
    u_target = tgt_m_minus;
    uint16_t l0 = model_from(LK - K - 50, u_follow);
    uint16_t m0 = battery_model_pm();
    pw_reset();
    run_pw(3600);
    uint16_t m1 = battery_model_pm(), l1 = battery_level_permille();
    CHECK(abs((int)m1 - (int)(m0 + K)) <= 10, "M after 1 h: %u -> %u, want +%d +-10", m0, m1, K);
    CHECK(abs((int)l1 - (int)m1) <= 2, "the display follows M with U above it: %u vs %u", l1, m1);
    CHECK(pw_fall == 0 && pw_rise_big == 0 && pw_ceiling == 0, "falls %d, big rises %d, past U %d", pw_fall,
          pw_rise_big, pw_ceiling);
    printf("  L0 %u, M %u -> %u in 1 h\n", l0, m0, m1);
}

/* Early clamp entry: L0 600, 5C at the clamp from the first minute. The 1 h
 * rise stays <= K_CC + 10 (round 1's formula started the tail at clamp entry). */
static void early_clamp(uint16_t l0) {
    u_target = tgt_clamp;
    model_from(l0, u_follow);
    uint16_t a = battery_level_permille();
    pw_reset();
    run_pw(3600);
    uint16_t b = battery_level_permille();
    CHECK(b - a <= K + 10, "1 h rise at the clamp %u -> %u, <= %d", a, b, K + 10);
    CHECK(pw_rise_big == 0 && pw_fall == 0 && pw_over_cap == 0, "rules: %d %d %d", pw_rise_big, pw_fall, pw_over_cap);
    printf("  L0 %u: %u -> %u in the first hour at the clamp\n", a, a, b);
}
static void m_early_clamp(void) {
    synthetic("L0 600, 5C clamped from the start");
    early_clamp(600);
}
/* The same 100 pm below the knee, wherever the header puts it: with B3's
 * L_KNEE (533) a start at 600 is above the knee, where the tail is entered
 * anyway, so only this one sees a tail started at the clamp. */
static void m_early_clamp_below(void) {
    synthetic("L0 = L_KNEE - 100, 5C clamped from the start");
    early_clamp(LK > 100 ? (uint16_t)(LK - 100) : 0u);
}

/* Near-full top-up: L0 950, FULL after 15 min -> the FULL step <= 50 pm. */
static void m_topup_near_full(void) {
    synthetic("on the pack at the clamp (the 950 guess), plugged in, FULL after 15 min");
    vdd_mv = 3900; c5 = 100;
    run_s(30);
    CHECK(battery_level_permille() == 950, "the clamp guess: %u", battery_level_permille());
    vdd_mv = 4300; chrg_low = true;
    run_s(15 * 60);
    uint16_t before = battery_level_permille();
    chrg_low = false; vdd_mv = 4470;
    run_s(30);
    CHECK(battery_level_permille() == 1000, "FULL: %u", battery_level_permille());
    CHECK(before >= 950 && 1000 - before <= 50, "the FULL step from %u is <= 50 pm", before);
}

/* Just full: 1000 stays 1000 through a top-up (the already-full exception). */
static void m_just_full(void) {
    become_full();
    CHECK(battery_level_permille() == 1000, "full");
    vdd_mv = 4300; chrg_low = true;
    pw_reset();
    run_pw(20 * 60);
    CHECK(battery_level_permille() == 1000 && pw_fall == 0, "a top-up keeps 1000: %u", battery_level_permille());
    CHECK(battery_chg_state() == ST_MODEL, "modeled as a top-up, no LOST: %u", battery_chg_state());
}

/* --- The cap and the clamp ---------------------------------------------------- */

/* The tail clock's entry for a start at l0 above the knee, by a plain scan of
 * the table (tail_grid.py's m_fw, second by second), not battery.c's node
 * search: the first second whose interpolated M, in 1/16 pm, is >= l0 * 16. */
static uint32_t tail_entry_scan(uint16_t l0) {
    for (uint32_t s = 0; s < TT; s++) {
        uint32_t i = s / 60u, f = s % 60u;
        uint32_t x = batt_tail_x16[i] + (uint32_t)(batt_tail_x16[i + 1] - batt_tail_x16[i]) * f / 60u;
        if (x >= (uint32_t)l0 * 16u) return s;
    }
    return TT;
}

/* Delayed termination at the clamp: L0 600, clamped throughout, CHRG held 2 h
 * past the model's own termination. <= 990 throughout; "Charge" exactly
 * T_OVERRUN after the tail clock reaches T_TAIL; 1000 at FULL. */
static void delayed(bool unplug_instead) {
    synthetic("L0 600, 5C clamped throughout, CHRG held 2 h past the model's termination");
    u_target = tgt_clamp;
    model_from(600, u_follow);
    uint16_t l0 = battery_level_permille();
    /* Below the knee, the knee comes at the first second whose L0 + K t / 3600
     * >= L_KNEE, and the tail clock starts there. Above it (L_KNEE 533 since
     * B3 trial 1), the tail clock enters at the first second whose M >= L0, so
     * OVERRUN comes (T_TAIL - entry) + T_OVERRUN in. */
    uint32_t s_knee = (l0 >= LK) ? 0 : (uint32_t)(((LK - l0) * 3600 + K - 1) / K);
    uint32_t entry  = (l0 >= LK) ? tail_entry_scan(l0) : 0;
    uint32_t want   = s_knee + TT - entry + BATTERY_T_OVERRUN_S;
    uint32_t lost_at = 0;
    pw_reset();
    for (uint32_t s = 1; s <= want + 2 * 3600 - BATTERY_T_OVERRUN_S + 60; s++) {
        run_pw(1);
        if (!lost_at && battery_chg_state() == ST_LOST) lost_at = s;
        if (unplug_instead && s == want - 60) break;
    }
    CHECK(pw_over_cap == 0, "<= 990 throughout: %d seconds over", pw_over_cap);
    if (unplug_instead) {
        vdd_mv = 3900; chrg_low = false;   /* unplugged at the clamp before FULL */
        run_s(BATTERY_RELAX_S + 30);
        CHECK(battery_level_permille() >= 905, "re-seated at the clamp: %u", battery_level_permille());
        return;
    }
    CHECK(lost_at && (lost_at + 1 >= want && lost_at <= want + 1), "OVERRUN at %u s, want %u +-1 (knee %u)",
          lost_at, want, s_knee);
    CHECK(battery_level_permille() == 0xFFFF, "\"Charge\" after OVERRUN");
    chrg_low = false; vdd_mv = 4470;
    run_s(30);
    CHECK(battery_level_permille() == 1000, "1000 at FULL: %u", battery_level_permille());
}
static void m_delayed_termination(void) { delayed(false); }
static void m_delayed_unplug(void) { delayed(true); }

/* --- The v5 log ---------------------------------------------------------------- */

/* The reply in a 29-byte buffer guarded on both sides; the period comes from
 * battery_cfg; the entry carries m and chg. */
static void m_log_v5(void) {
    u_target = tgt_m_minus; u_delta = -100;
    model_from(400, u_follow);
    run_s(11 * 60);
    uint8_t buf[2 + 29 + 2];
    memset(buf, 0xA5, sizeof buf);
    battery_log_read(0, buf + 2);
    CHECK(buf[0] == 0xA5 && buf[1] == 0xA5 && buf[31] == 0xA5 && buf[32] == 0xA5, "the reply stays inside its 29 bytes");
    const uint8_t *o = buf + 2;
    CHECK(o[0] == 5, "log v5: %u", o[0]);
    uint16_t count = (uint16_t)(o[1] | o[2] << 8), written = (uint16_t)(o[9] | o[10] << 8);
    CHECK(count >= 1 && written == count, "count %u written %u", count, written);
    const uint8_t *e = o + 11;
    uint8_t m = e[16], chg = e[17];
    CHECK((chg & 7) == ST_MODEL && m != 0xFF, "the entry's chg state MODEL and m %u: chg %02x", m, chg);
    uint8_t cfg[8];
    battery_cfg(0, 0, 0, cfg);
    CHECK((cfg[6] | cfg[7] << 8) == 600, "the period from HC_BATTCFG: %u", cfg[6] | cfg[7] << 8);
}

/* 661 reports of 99, then 100s: c5_max must reach 100 with the saturated bit
 * set (the sum stops accepting at ~661 x 99). */
static void m_log_saturated(void) {
    synthetic("661 reports of 99 then 100s, inside one period");
    vdd_mv = 3900; c5 = 0xFF;
    run_s(5);
    for (int i = 0; i < 661; i++) deliver(99);
    for (int i = 0; i < 20; i++) deliver(100);
    run_s(10 * 60);
    uint8_t o[29];
    battery_log_read(0, o);
    const uint8_t *e = o + 11;
    CHECK(e[8] == 100, "c5_max 100: %u", e[8]);
    CHECK(e[17] & 0x80, "the saturated bit: chg %02x", e[17]);
}

/* --- The ceiling (SYNTHETIC) --------------------------------------------------- */

/* Count, second by second, what LOST (a) accumulates: fresh below-clamp
 * seconds with M - U > LOST_PM; the clamp and stale seconds hold the count. */
static uint32_t acc_a;
static uint32_t lost_second;   /* the second LOST was first seen, 0 = never */
static uint32_t acc_at_lost;
static uint32_t secs;
static void run_lost(uint32_t s) {
    for (uint32_t i = 0; i < s; i++) {
        run_pw(1);
        secs++;
        int u = u_now();
        uint16_t m = battery_model_pm();
        if (u >= 0 && m != 0xFFFFu) acc_a = ((int)m - u > (int)BATTERY_LOST_PM) ? acc_a + 1 : 0;
        if (!lost_second && battery_chg_state() == ST_LOST) { lost_second = secs; acc_at_lost = acc_a; }
    }
}
static void ceil_start(int l0) {
    u_target = tgt_m_minus; u_delta = -100;
    model_from(l0, u_follow);
    run_s(5 * 60);
    pw_reset(); acc_a = 0; lost_second = 0; secs = 0;
}

static void m_ceil_hold30(void) {
    synthetic("from ~300: U 100 above M, then U = M - 30 for 20 min");
    ceil_start(300);
    u_delta = 30;
    run_lost(20 * 60);
    CHECK(lost_second == 0, "M - U = 30 never LOSTs");
    CHECK(pw_fall == 0 && pw_ceiling == 0 && pw_rise_big == 0, "held: falls %d, past U %d, big %d", pw_fall,
          pw_ceiling, pw_rise_big);
}

static void m_ceil_60_29(void) {
    synthetic("U = M - 65 for 29 min, then U above M");
    ceil_start(300);
    u_delta = 65;
    run_lost(29 * 60);
    u_delta = -50;
    run_lost(15 * 60);
    CHECK(lost_second == 0, "29 min of M - U > 50 is not LOST");
}

static void m_ceil_60_30(void) {
    synthetic("U = M - 65 until LOST");
    ceil_start(300);
    u_delta = 65;
    run_lost(40 * 60);
    CHECK(lost_second != 0, "LOST fired");
    CHECK(acc_at_lost + 5 >= BATTERY_LOST_S && acc_at_lost <= BATTERY_LOST_S + 5,
          "LOST after %u accumulated seconds of M - U > 50, want %u +-5", acc_at_lost, BATTERY_LOST_S);
    CHECK(battery_level_permille() == 0xFFFF, "\"Charge\" once LOST");
}

/* 20 min of M - U = 65, 5 min at the clamp, 10 more of 65: LOST, because the
 * clamp HOLDS the timer (a reset there would need 30 more minutes). The steps
 * into and out of the clamp are made clean -- the reports pause 25 s, so the
 * ring empties and the next estimate is the new value -- because a 64-report
 * mean ramping through U >= M - 50 is a fresh below-clamp second, which
 * rightly RESETS the timer. Stale seconds hold it too. */
static int clamp_phase;   /* 0: M - 65, 1: no reports, 2: the clamp */
static int tgt_clamp_steps(void) { return clamp_phase == 1 ? 200000 : clamp_phase == 2 ? 5000 : tgt_m_minus(); }
static void m_ceil_clamp_hold(void) {
    synthetic("20 min of M - U = 65, 5 min clamped, then 65 again (25 s report gaps at each step)");
    ceil_start(300);
    u_delta = 65; clamp_phase = 0; u_target = tgt_clamp_steps;
    run_lost(20 * 60);
    uint32_t before = acc_a;
    clamp_phase = 1; run_lost(25);
    clamp_phase = 2; run_lost(5 * 60);
    clamp_phase = 1; run_lost(25);
    clamp_phase = 0;
    uint32_t back = secs;
    run_lost(15 * 60);
    CHECK(lost_second != 0 && lost_second > back, "LOST in the second stretch (at %u s, back at %u)", lost_second, back);
    CHECK(lost_second && lost_second - back + before + 30 >= BATTERY_LOST_S && lost_second - back + before <= BATTERY_LOST_S + 90,
          "the clamp held the %u s accumulated before it: LOST %u s after it", before, lost_second - back);
}

/* Clamp entry while the ceiling binds: a count-up at <= 1 pm/s to M. */
static void m_ceil_clamp_entry(void) {
    synthetic("U = M - 30 for 10 min (binding), then the clamp");
    ceil_start(300);
    u_delta = 30;
    run_lost(10 * 60);
    u_target = tgt_clamp;
    pw_reset();
    run_pw(10 * 60);
    uint16_t m = battery_model_pm(), l = battery_level_permille();
    CHECK(pw_rise_big == 0 && pw_fall == 0, "count-up at <= 1 pm/s: big rises %d", pw_rise_big);
    CHECK(l + 1 >= m && l <= m, "up to M: level %u, M %u", l, m);
}

/* Clamp exit with U below the display: it holds, and the timer runs (a). */
static void m_ceil_clamp_exit(void) {
    synthetic("at the clamp 10 min, then U = M - 65");
    u_target = tgt_clamp;
    model_from(300, u_follow);
    run_s(10 * 60);
    pw_reset(); acc_a = 0; lost_second = 0; secs = 0;
    u_target = tgt_m_minus; u_delta = 65;
    run_lost(40 * 60);
    CHECK(pw_fall == 0 && pw_ceiling == 0, "held: falls %d, past U %d", pw_fall, pw_ceiling);
    CHECK(lost_second != 0 && acc_at_lost + 5 >= BATTERY_LOST_S && acc_at_lost <= BATTERY_LOST_S + 5,
          "LOST after %u accumulated seconds", acc_at_lost);
}

/* Reports lost: 9 min, no rise and then a catch-up; 10 min, LOST. */
static int stopped;
static int tgt_stoppable(void) { return stopped ? 200000 : tgt_m_minus(); }
static void reports_lost(uint32_t gap_s, bool expect_lost) {
    synthetic("reports stop for a while, then resume");
    u_target = tgt_stoppable; u_delta = -100; stopped = 0;
    model_from(300, u_follow);
    run_s(5 * 60);
    stopped = 1;
    uint16_t at_stop = battery_level_permille();
    uint32_t stale_from = 0, lost_at = 0;
    for (uint32_t i = 1; i <= gap_s; i++) {
        run_s(1);
        if (!stale_from && battery_5c_x100() == 0xFFFF) stale_from = i;
        if (!lost_at && battery_chg_state() == ST_LOST) lost_at = i;
    }
    uint16_t at_resume = battery_level_permille();
    if (expect_lost) {
        CHECK(lost_at && stale_from && lost_at - stale_from + 2 >= BATTERY_STALE_LOST_S &&
              lost_at - stale_from <= BATTERY_STALE_LOST_S + 2, "LOST %u s after going stale (%u), want %u",
              lost_at - stale_from, stale_from, BATTERY_STALE_LOST_S);
        return;
    }
    CHECK(lost_at == 0, "no LOST in %u s", gap_s);
    CHECK(at_resume <= at_stop + 25, "no rise while stale (the first 20 s were fresh): %u -> %u", at_stop, at_resume);
    stopped = 0;
    pw_reset();
    run_pw(5 * 60);
    CHECK(pw_rise_big == 0 && battery_level_permille() > at_resume, "a catch-up at <= 1 pm/s: %u -> %u",
          at_resume, battery_level_permille());
}
static void m_reports_lost_9(void) { reports_lost(9 * 60, false); }
static void m_reports_lost_10(void) { reports_lost(11 * 60, true); }

/* --- Pauses (SYNTHETIC), on the final PAUSE_S and RELAX_S ----------------------- */

static void pause_for(uint32_t s) {
    chrg_low = false; vdd_mv = 4470;
    run_s(s);
    chrg_low = true; vdd_mv = 4193;
}

/* A pause short of PAUSE_S: the display holds; M and the timers continue
 * from where they stopped, with no jump and no requalification. */
static void m_pause_short(void) {
    synthetic("a charger pause of PAUSE_S - 60 s below the clamp");
    u_target = tgt_m_minus; u_delta = -100;
    model_from(300, u_follow);
    run_s(5 * 60);
    uint16_t m0 = battery_model_pm(), l0 = battery_level_permille();
    pause_for(BATTERY_PAUSE_S - 60);
    CHECK(battery_level_permille() == l0, "the display held: %u -> %u", l0, battery_level_permille());
    run_s(3);
    CHECK(battery_chg_state() == ST_MODEL, "still MODEL, no requalification: %u", battery_chg_state());
    uint16_t m1 = battery_model_pm();
    CHECK(m1 >= m0 && m1 <= m0 + 2, "M continued from where it stopped: %u -> %u", m0, m1);
}

/* A resumption 1 s before PAUSE_S continues; 2 s after, it requalifies at
 * 60 s from the adopted level. (The pause clock starts at the first 1 Hz tick
 * after charging_now() drops, itself 1 s after CHRG: the handover comes
 * PAUSE_S + [0, 1) s after CHRG is released.) */
static void pause_edge(bool after) {
    synthetic(after ? "a pause 2 s past PAUSE_S" : "a pause 1 s short of PAUSE_S");
    u_target = tgt_m_minus; u_delta = -100;
    model_from(300, u_follow);
    run_s(5 * 60);
    pause_for(after ? BATTERY_PAUSE_S + 2 : BATTERY_PAUSE_S - 1);
    run_s(2);
    if (!after) {
        CHECK(battery_chg_state() == ST_MODEL, "continues: %u", battery_chg_state());
        return;
    }
    uint16_t adopted = battery_level_permille();
    CHECK(battery_chg_state() == ST_NONE && adopted != 0xFFFF, "handed over, a level adopted: %u %u",
          battery_chg_state(), adopted);
    run_s(50);
    CHECK(battery_chg_state() == ST_NONE, "requalifying: %u", battery_chg_state());
    run_s(15);
    CHECK(battery_chg_state() == ST_MODEL, "MODEL again after 60 s: %u", battery_chg_state());
}
static void m_pause_before(void) { pause_edge(false); }
static void m_pause_after(void) { pause_edge(true); }

/* At the handover, reports still falling before RELAX_S are not adopted. */
static int relax_phase;
static int tgt_relaxing(void) { return relax_phase == 0 ? m_now() + 100 : relax_phase == 1 ? 600 : 400; }
static void m_pause_relaxing(void) {
    synthetic("during a long pause the voltage reads 600-worth until RELAX_S - 20 s, then settles at 400-worth");
    relax_phase = 0;
    u_target = tgt_relaxing;
    model_from(300, u_follow);
    run_s(5 * 60);
    uint16_t held = battery_level_permille();
    chrg_low = false; vdd_mv = 4470; relax_phase = 1;
    run_s(BATTERY_RELAX_S - 20);
    relax_phase = 2;
    run_s(BATTERY_PAUSE_S - BATTERY_RELAX_S + 60);
    uint16_t l = battery_level_permille();
    CHECK(battery_chg_state() == ST_NONE, "handed over: %u", battery_chg_state());
    CHECK(abs((int)l - 400) <= 12, "adopted the settled 400-worth, not the relaxing 600: %u (held %u)", l, held);
}

/* Reports missing at PAUSE_S: hold until a qualifying estimate, then adopt. */
static void m_pause_missing(void) {
    synthetic("reports stop at the pause, return 5 min after PAUSE_S");
    u_target = tgt_stoppable; u_delta = -100; stopped = 0;
    model_from(300, u_follow);
    run_s(5 * 60);
    uint16_t held = battery_level_permille();
    chrg_low = false; vdd_mv = 4470; stopped = 1;
    run_s(BATTERY_PAUSE_S + 5 * 60);
    CHECK(battery_chg_state() == ST_NONE && battery_level_permille() == held, "held with nothing to adopt: %u -> %u",
          held, battery_level_permille());
    stopped = 0; u_target = tgt_fixed; tgt_fixed_pm = 350;
    run_s(60);
    CHECK(abs((int)battery_level_permille() - 350) <= 12, "then adopted: %u", battery_level_permille());
}

/* The handover from LOST and from UNKNOWN-CHG: a number once adopted. */
static void m_pause_from_lost(void) {
    synthetic("LOST (reports stopped 11 min), then a long pause");
    u_target = tgt_stoppable; u_delta = -100; stopped = 0;
    model_from(300, u_follow);
    run_s(60);
    stopped = 1;
    run_s(11 * 60);
    CHECK(battery_chg_state() == ST_LOST, "LOST: %u", battery_chg_state());
    stopped = 0; u_target = tgt_fixed; tgt_fixed_pm = 380;
    chrg_low = false; vdd_mv = 4470;
    run_s(BATTERY_PAUSE_S + 60);
    CHECK(battery_chg_state() == ST_NONE && battery_level_permille() != 0xFFFF, "a number adopted: %u",
          battery_level_permille());
}
static void m_pause_from_unknown(void) {
    synthetic("UNKNOWN-CHG (a boot on USB at the clamp), then a long pause at 380-worth");
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(120);
    CHECK(battery_chg_state() == ST_UNKNOWN, "UNKNOWN-CHG: %u", battery_chg_state());
    c5 = 0xFF; u_target = tgt_fixed; tgt_fixed_pm = 380; c5_src = u_follow;
    chrg_low = false; vdd_mv = 4470;
    run_s(BATTERY_PAUSE_S + 60);
    CHECK(battery_level_permille() != 0xFFFF, "a number adopted: %u", battery_level_permille());
}

/* A handover, then an unplug: `session` is still set, so the re-seat is owed. */
static void m_pause_then_unplug(void) {
    synthetic("a handover, then unplugged; the pack reads 450-worth");
    u_target = tgt_m_minus; u_delta = -100;
    model_from(300, u_follow);
    run_s(5 * 60);
    chrg_low = false; vdd_mv = 4470;
    run_s(BATTERY_PAUSE_S + 60);
    u_target = tgt_fixed; tgt_fixed_pm = 450;
    vdd_mv = 3900;
    run_s(BATTERY_RELAX_S + 40);
    CHECK(abs((int)battery_level_permille() - 450) <= 12, "re-seated at 450 (once, upward allowed): %u",
          battery_level_permille());
}

/* --- LOST, the re-seat, FULL ---------------------------------------------------- */

/* A slow charge: U rising at half the modeled rate. LOST once M - U has been
 * over LOST_PM for LOST_S. (A test of LOST, not a qualification of supplies.) */
static uint32_t slow_from;
static int tgt_half(void) { return 300 + (int)((secs - slow_from) * (uint32_t)K / 7200u); }
static void m_slow_charge(void) {
    synthetic("5C rising at half the modeled rate");
    u_target = tgt_m_minus; u_delta = 0;
    model_from(300, u_follow);
    acc_a = 0; lost_second = 0; secs = 0; slow_from = 0;
    u_target = tgt_half;
    pw_reset();
    run_lost(3 * 3600);
    CHECK(lost_second != 0, "LOST fired");
    CHECK(acc_at_lost + 5 >= BATTERY_LOST_S && acc_at_lost <= BATTERY_LOST_S + 5, "after %u accumulated seconds",
          acc_at_lost);
    printf("  LOST at %u s (%.1f h)\n", lost_second, lost_second / 3600.0);
}

/* The re-seat: unplug after a real session; resolved by the first estimate
 * from reports RELAX_S after the unplug. */
static void reseat_case(int l0, int relaxed_pm, int expect) {
    u_target = tgt_m_minus; u_delta = -100;
    model_from(l0, u_follow);
    run_s(90);
    u_target = tgt_fixed; tgt_fixed_pm = relaxed_pm;
    vdd_mv = 3900; chrg_low = false;
    uint16_t at_unplug = battery_level_permille();
    run_s(BATTERY_RELAX_S - 10);
    CHECK(battery_level_permille() == at_unplug, "owed, held through RELAX_S: %u -> %u", at_unplug,
          battery_level_permille());
    run_s(40);
    CHECK(abs((int)battery_level_permille() - expect) <= 12, "re-seated from %u to %d-worth: %u", at_unplug, expect,
          battery_level_permille());
}
static void m_reseat_up(void) { synthetic("charging at ~700, the relaxed pack worth 850"); reseat_case(700, 850, 850); }
static void m_reseat_down(void) { synthetic("charging at ~850, the relaxed pack worth 700"); reseat_case(850, 700, 700); }
static void m_reseat_clamp(void) {
    synthetic("charging at ~880, the pack still at the clamp long after the unplug");
    reseat_case(880, 5000, 905);
}
static void m_reseat_unknown(void) {
    synthetic("an UNKNOWN-CHG session unplugged at the clamp");
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(120);
    vdd_mv = 3900; chrg_low = false;
    run_s(BATTERY_RELAX_S + 40);
    CHECK(battery_level_permille() == 950, "UNKNOWN at the clamp -> 950: %u", battery_level_permille());
}
static void m_reseat_lost(void) {
    synthetic("a LOST session unplugged; the pack at the clamp");
    u_target = tgt_stoppable; u_delta = -100; stopped = 0;
    model_from(300, u_follow);
    stopped = 1;
    run_s(11 * 60);
    CHECK(battery_chg_state() == ST_LOST, "LOST");
    stopped = 0; u_target = tgt_clamp;
    vdd_mv = 3900; chrg_low = false;
    run_s(BATTERY_RELAX_S + 40);
    CHECK(battery_level_permille() == 950, "LOST re-seats as UNKNOWN -> 950: %u", battery_level_permille());
}
static void m_reseat_missing(void) {
    synthetic("unplugged with no reports until 5 min past RELAX_S");
    u_target = tgt_stoppable; u_delta = -100; stopped = 0;
    model_from(600, u_follow);
    run_s(90);
    uint16_t l = battery_level_permille();
    stopped = 1;
    vdd_mv = 3900; chrg_low = false;
    run_s(BATTERY_RELAX_S + 5 * 60);   /* stale until well past RELAX_S */
    CHECK(battery_level_permille() == l, "owed while stale: %u", battery_level_permille());
    stopped = 0; u_target = tgt_fixed; tgt_fixed_pm = 520;
    run_s(60);
    CHECK(abs((int)battery_level_permille() - 520) <= 12, "then resolved: %u", battery_level_permille());
}
static void m_reseat_replugs(void) {
    synthetic("unplug 30 s, replug 30 s, three times, then stay unplugged");
    u_target = tgt_m_minus; u_delta = -100;
    model_from(600, u_follow);
    run_s(90);
    u_target = tgt_fixed; tgt_fixed_pm = 520;
    for (int k = 0; k < 3; k++) {
        vdd_mv = 3900; chrg_low = false; run_s(30);
        vdd_mv = 4193; chrg_low = true; run_s(30);
    }
    uint16_t l = battery_level_permille();
    vdd_mv = 3900; chrg_low = false;
    run_s(BATTERY_RELAX_S - 10);
    CHECK(battery_level_permille() == l, "still owed, RELAX_S restarted at the last unplug: %u", battery_level_permille());
    run_s(40);
    CHECK(abs((int)battery_level_permille() - 520) <= 12, "resolved once: %u", battery_level_permille());
}
/* 09-29: the first post-unplug reports were still at the clamp, and the old
 * code spent the re-seat on them. Here they fall inside RELAX_S. */
static int phase0929;
static int tgt_0929(void) { return phase0929 == 0 ? 5000 : 760; }
static void m_reseat_0929(void) {
    synthetic("after the unplug: 60 s still at the clamp, then 760-worth");
    u_target = tgt_m_minus; u_delta = -100;
    model_from(820, u_follow);
    run_s(90);
    phase0929 = 0; u_target = tgt_0929;
    vdd_mv = 3900; chrg_low = false;
    run_s(60);
    phase0929 = 1;
    run_s(BATTERY_RELAX_S + 40);
    CHECK(abs((int)battery_level_permille() - 760) <= 12, "re-seated from the voltage, not the clamp: %u",
          battery_level_permille());
}

/* FULL is a heuristic: a charger fault with 5C clamped reads FULL. */
static void m_full_fault(void) {
    synthetic("charging at the clamp, then CHRG released by a fault (VDD still external)");
    u_target = tgt_clamp;
    model_from(700, u_follow);
    run_s(10 * 60);
    chrg_low = false; vdd_mv = 4470;
    run_s(30);
    CHECK(battery_chg_state() == ST_FULL && battery_level_permille() == 1000, "reads FULL (documented): %u %u",
          battery_chg_state(), battery_level_permille());
}

/* FULL holds once it is reached. The pause before it starts RELAX_S; that
 * timer must not empty the ring after FULL, or FULL drops until the ring
 * refills (10-01's replay: 18 s at 1000 reading NONE). */
static void m_full_holds(void) {
    synthetic("charging at the clamp, CHRG released (termination), then 30 min on USB");
    u_target = tgt_clamp;
    model_from(800, u_follow);
    run_s(10 * 60);
    chrg_low = false; vdd_mv = 4470;
    int seen = 0, dropped = 0;
    for (int i = 0; i < 30 * 60; i++) {
        run_s(1);
        if (battery_chg_state() == ST_FULL) seen = 1;
        else if (seen) dropped++;
    }
    CHECK(seen, "FULL reached");
    CHECK(dropped == 0, "FULL held: %d seconds not FULL after it", dropped);
    CHECK(battery_level_permille() == 1000, "1000 at FULL: %u", battery_level_permille());
}

/* OVERRUN timing at one start, for tail_fw_grid.py, which runs it at every grid
 * point and checks the time against the tail clock: (T_TAIL - entry) +
 * T_OVERRUN from a start above the knee, knee + T_TAIL + T_OVERRUN from below.
 * 5C is clamped throughout, so neither LOST condition (a) nor (b) can fire:
 * the "Charge" seen is OVERRUN's. Prints the level the session opened at and
 * the charging second "Charge" came, counted as delayed() counts them. */
static void m_overrun(const char *arg) {
    int l0 = atoi(arg);
    u_target = tgt_clamp;
    uint16_t at = model_from(l0, u_follow);
    uint32_t limit = (uint32_t)(1000u * 3600u / (unsigned)K) + TT + BATTERY_T_OVERRUN_S + 600u, lost = 0;
    for (uint32_t s = 1; s <= limit && !lost; s++) {
        run_s(1);
        if (battery_chg_state() == ST_LOST) lost = s;
    }
    CHECK(lost, "OVERRUN fired within %u s", limit);
    CHECK(battery_level_permille() == 0xFFFF, "\"Charge\" after OVERRUN: %u", battery_level_permille());
    printf("  OVERRUN %u %u\n", at, lost);
}

/* --- Replays: the recorded charges from flat ------------------------------------ */

static uint16_t rr_prev, rr_last_before_full;
static int rr_big, rr_fall, rr_over, rr_ceiling, rr_full_seen, rr_lost;
static void rr_hook(void) {
    uint16_t l = battery_level_permille();
    uint8_t st = battery_chg_state();
    if (st == ST_LOST) rr_lost++;
    if (st == ST_FULL) {
        if (!rr_full_seen) rr_full_seen = 1;
    } else if (l != 0xFFFFu) {
        if (rr_prev != 0xFFFFu) {
            if (l < rr_prev) rr_fall++;
            if (l > rr_prev + 1u) rr_big++;
            int u = u_now();
            if (l > rr_prev && u >= 0 && (int)l > u) rr_ceiling++;
        }
        if (l > BATTERY_MODEL_CAP) rr_over++;
        rr_last_before_full = l;
    }
    rr_prev = l;
}
static void replay_model(const char *name, const char *path, bool tail_0928) {
    rr_prev = 0xFFFF; rr_last_before_full = 0; rr_big = rr_fall = rr_over = rr_ceiling = rr_full_seen = rr_lost = 0;
    rp_second_hook = rr_hook;
    int off = rp_run(path);
    if (off < 0) return;
    CHECK(battery_chg_state() != ST_UNKNOWN, "%s: not UNKNOWN-CHG (FROM-FLAT on its reconstruction)", name);
    if (tail_0928) {
        synthetic("09-28's tail: 2 h at the clamp, charging, then CHRG released (~12:32)");
        vdd_mv = 4300; vdd_dip_mv = 0; c5 = 100; chrg_low = true;
        for (int i = 0; i < 2 * 3600; i++) { run_s(1); rr_hook(); }
        chrg_low = false; vdd_mv = 4470;
        for (int i = 0; i < 30; i++) { run_s(1); rr_hook(); }
    }
    rp_table(tail_0928 ? 60 : 3);
    CHECK(off == 0, "%s: EXTERNAL throughout", name);
    CHECK(rr_big == 0 && rr_fall == 0, "%s: no step > 1 pm/s (%d), no fall (%d)", name, rr_big, rr_fall);
    CHECK(rr_ceiling == 0, "%s: no rise past a fresh U: %d", name, rr_ceiling);
    CHECK(rr_over == 0, "%s: <= 990 until FULL: %d seconds over", name, rr_over);
    CHECK(rr_lost == 0, "%s: LOST or OVERRUN never fire: %d seconds LOST", name, rr_lost);
    if (rr_full_seen) {
        CHECK(rr_last_before_full >= 970, "%s: the last value before FULL >= 970: %u", name, rr_last_before_full);
        CHECK(battery_level_permille() == 1000, "%s: 1000 at FULL", name);
    }
    printf("  %s: last before FULL %u pm, FULL %s\n", name, rr_last_before_full, rr_full_seen ? "seen" : "not in the log");
}
static void m_replay_0928(const char *p) { replay_model("09-28", p, true); }
static void m_replay_1001(const char *p) { replay_model("10-01", p, false); }
static void m_replay_1004a(const char *p) { replay_model("10-04", p, false); }
