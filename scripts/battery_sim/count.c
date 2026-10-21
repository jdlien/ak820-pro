/* Phase 2's energy count (battery.c; plans/PHASE2-BUILD-PLAN.md, section 1,
 * and codex's must-fix 8), #included by sim.c after ladder.c. The sim's load
 * unless a scenario changes it: full white (81 channels of each colour at 255,
 * the per-colour model of 10-19 refitted for 81 LEDs on 10-21: 8.64 + 20655 x
 * (3.681 + 2.565 + 2.322) uW = 185.6 mW, as 82 x the old slopes gave), the backlight at level 10 (duty 10/48: 8.15 mW) and the base
 * (106.9): 300.65 mW, so 1 pm every 186.5 s and ~19.30 pm an hour. */

#define SIM_MW        300.65
#define PM_PER_HOUR   (SIM_MW * 3600.0 / 56084.4)   /* ~19.30 */

/* On the pack with a level from the first estimate at `c5v`. */
static void c_start(uint8_t c5v) {
    vdd_mv = 3900; c5 = c5v;
    run_s(30);
}

/* 5C 96 is 4001.5 mV, mid-plateau: curve 689 pm, the band 613..844. */
static void c_rate(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    uint32_t e0 = battery_energy_used_mwh_x10();
    CHECK(l0 >= 680 && l0 <= 700, "the first estimate's level ~689: %u", l0);
    run_s(3600);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR) <= 1.0, "an hour at %.1f mW is %.1f pm: %.0f", SIM_MW, PM_PER_HOUR, drop);
    uint32_t de = battery_energy_used_mwh_x10() - e0;
    CHECK(fabs(de - SIM_MW * 10.0) <= 5.0, "and %.1f mWh of modelled energy: %u x 0.1", SIM_MW, de);
    CHECK(battery_count_state() == BATTERY_COUNT_RUN, "counting: state %u", battery_count_state());
    uint32_t p = battery_power_uw();
    CHECK(fabs(p - SIM_MW * 1000.0) <= 800.0, "the draw now: %u uW", p);
}

/* Elapsed time, not ticks (codex): housekeeping that runs late now and then
 * still counts the right energy. */
static void c_uneven(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    uint32_t t_end = now_ms + 3600000u;
    for (uint32_t k = 0; (int32_t)(t_end - now_ms) > 0; k++) {
        if (k % 7 == 3) now_ms += 1200;   /* a slow pass: 1.3 s between two ticks */
        tick();
    }
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR) <= 1.0, "uneven ticks, still %.1f pm an hour: %.0f", PM_PER_HOUR, drop);
}

/* The 32-bit ms timer wraps mid-count. */
static void c_wrap(void) {
    /* ~30 min before the wrap, on the 2.5 s report schedule's phase (tick()
     * delivers a report when now_ms % 2500 == 0). */
    now_ms = 4293165000u;
    c_start(96);
    uint16_t l0 = battery_level_permille();
    run_s(3600);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR) <= 1.0, "across the wrap, %.1f pm an hour: %.0f", PM_PER_HOUR, drop);
}

/* Below the band the level waits, the energy keeps counting, and the wait's
 * energy is dropped, not banked (codex must-fix 6). 5C 80 (3861 mV) gives
 * ~380 pm; 5C 88 (3931 mV) puts the band's lower edge (the curve 40 mV
 * below, less 15 pm) at ~476. */
static void c_hold(void) {
    c_start(80);
    uint16_t l0 = battery_level_permille();
    c5 = 88;
    run_s(120);
    uint16_t l1 = battery_level_permille();
    uint32_t e1 = battery_energy_used_mwh_x10();
    run_s(3600);
    CHECK(battery_level_permille() == l1, "held below the band for an hour: %u -> %u", l1,
          battery_level_permille());
    CHECK(battery_count_state() == BATTERY_COUNT_HELD, "state HELD: %u", battery_count_state());
    CHECK(battery_energy_used_mwh_x10() - e1 >= SIM_MW * 10.0 - 10.0, "the energy still counted: %u",
          battery_energy_used_mwh_x10() - e1);
    c5 = 80;
    run_s(600);
    double drop = l1 - battery_level_permille();
    CHECK(drop <= PM_PER_HOUR / 6 + 1.5, "after the hold, the normal rate, no rush: %.0f pm in 10 min", drop);
    CHECK(l0 >= l1, "never rose: %u then %u", l0, l1);
}

/* Above the band the ratchet eases the level down to its top, at most 1% a
 * step, and the count rebases there. 5C 97 (4010.2 mV, ~802), then 5C 85
 * (3904.9 mV): the band's top ~536. */
static void c_ratchet(void) {
    c_start(97);
    uint16_t l0 = battery_level_permille();
    watch_reset();
    c5 = 85;
    run_s(60);
    CHECK(l0 - battery_level_permille() <= 50, "eases: %u pm in the first minute", l0 - battery_level_permille());
    run_s(900);
    int hi = (int)battery_curve_pm(battery_pack_mv() + BATTERY_BAND_MV_UP) + BATTERY_BAND_PM;
    CHECK(abs((int)battery_level_permille() - hi) <= 6, "down to the band's top %d: %u", hi,
          battery_level_permille());
    CHECK(w_big == 0, "never more than 1%% a step: %d big steps", w_big);
}

/* The count stops at 1%; the cut's latch sets 0, and time left goes. */
static void c_floor_cut(void) {
    c_start(40);   /* 3515 mV: ~28 pm */
    run_s(3 * 3600);
    CHECK(battery_level_permille() == 10, "the count stops at 1%%: %u", battery_level_permille());
    CHECK(battery_level_pct() == 1, "shows 1%%: %u", battery_level_pct());
    CHECK(!power_lights_cut(), "no cut yet above 3400 mV");
    c5 = 3;   /* 3187 mV; the 64-report estimate takes a few minutes to get there */
    run_s(300);
    CHECK(power_lights_cut(), "the cut");
    CHECK(battery_level_permille() == 0, "0 at the cut: %u", battery_level_permille());
    run_s(120);
    CHECK(battery_count_state() == BATTERY_COUNT_CUT, "state CUT: %u", battery_count_state());
    CHECK(battery_time_left_min() == 0xFFFF, "no time left after the cut: %u", battery_time_left_min());
}

/* Time left: level x energy per pm / the average draw. Young before an hour,
 * hidden on USB, the average frozen there. */
static void c_time_left(void) {
    c_start(96);
    run_s(59 * 60);
    CHECK(battery_avg_minutes() == 59, "59 minutes of average: %u", battery_avg_minutes());
    run_s(3 * 60);
    uint16_t lv = battery_level_permille();
    double want = lv * 56084.4 / SIM_MW / 60.0;
    uint16_t got = battery_time_left_min();
    CHECK(fabs(got - want) <= want * 0.02 + 2, "time left %u min, want %.0f", got, want);
    uint32_t avg = battery_power_avg_uw();
    CHECK(fabs(avg - SIM_MW * 1000.0) <= 800.0, "the average %u uW", avg);
    uint16_t mins = battery_avg_minutes();
    become_full();
    run_s(1800);
    CHECK(battery_time_left_min() == 0xFFFF, "hidden on USB: %u", battery_time_left_min());
    CHECK(battery_avg_minutes() == mins && battery_power_avg_uw() == avg, "frozen on USB: %u min, %u uW",
          battery_avg_minutes(), battery_power_avg_uw());
    CHECK(battery_energy_used_mwh_x10() == 0, "FULL restarts the energy: %u", battery_energy_used_mwh_x10());
}

/* The ladder's dark stage, Balanced's at 20 min: the RGB's energy leaves the
 * count (the driver's scale 0) and so does the backlight's, the base alone
 * (106.9 mW) for an hour, the deep sleep never taken (the sim has none). */
static void c_load_step(void) {
    power_init();
    c_start(96);
    idle_ms = 1200000;
    ltick();
    CHECK(power_stage() == POWER_STAGE_SCREEN_OFF, "dark: %d", power_stage());
    uint16_t l0 = battery_level_permille();
    for (uint32_t i = 0; i < 36000u; i++) ltick();
    CHECK(battery_power_uw() == 106900u, "the base alone: %u uW", battery_power_uw());
    double want = 106.9 * 3600.0 / 56084.4;
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - want) <= 1.0, "an hour dark: %.0f pm, want %.1f", drop, want);
}

#ifdef AK820_DEV_HOOKS
/* The RGB-off stage no mode reaches now, held by the bench: the base and the
 * backlight capped at level 4, 106.9 + 3.3 mW. */
static void c_lights_off_held(void) {
    power_init();
    c_start(96);
    power_force_stage(POWER_STAGE_LIGHTS_OFF);
    ltick();
    CHECK(power_stage() == POWER_STAGE_LIGHTS_OFF, "lights off, held: %d", power_stage());
    uint16_t l0 = battery_level_permille();
    for (uint32_t i = 0; i < 36000u; i++) ltick();
    CHECK(battery_power_uw() == 106900u + 39100u * 4u / 48u, "the base and level 4: %u uW", battery_power_uw());
    double want = (106.9 + 39.1 * 4 / 48) * 3600.0 / 56084.4;
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - want) <= 1.0, "an hour with the lights off: %.0f pm, want %.1f", drop, want);
}
#endif

/* The bench's USB data adds its 7.1 mW. */
static void c_usb_data(void) {
    usb_configured = true;
    c_start(96);
    uint32_t e0 = battery_energy_used_mwh_x10();
    run_s(3600);
    uint32_t de = battery_energy_used_mwh_x10() - e0;
    CHECK(fabs(de - (SIM_MW + 7.1) * 10.0) <= 5.0, "with USB data, %.1f mWh: %u x 0.1", SIM_MW + 7.1, de);
}

/* Stale reports: the count runs on, the band holds as it was, and the
 * recovery moves nothing at once. */
static void c_stale(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    c5 = 0xFF;   /* silent */
    run_s(15 * 60);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR / 4) <= 1.0, "counting while stale: %.0f pm in 15 min", drop);
    uint16_t l1 = battery_level_permille();
    c5 = 96;
    run_s(60);
    CHECK(abs((int)l1 - (int)battery_level_permille()) <= 1, "no jump at the recovery: %u -> %u", l1,
          battery_level_permille());
}

/* A 30 s excursion of 10 counts low on the steep part: the trimmed mean and
 * the ratchet's six estimates keep it to at most 1%. */
static void c_excursion(void) {
    c_start(80);   /* 3861 mV: ~380 pm */
    uint16_t l0 = battery_level_permille();
    c5 = 70;
    run_s(30);
    c5 = 80;
    run_s(300);
    double want = PM_PER_HOUR * 330 / 3600;
    double extra = (l0 - battery_level_permille()) - want;
    CHECK(extra <= 10.5, "the excursion cost at most 1%%: %.1f pm beyond the count", extra);
}

/* A sustained bias of ~+15 mV (two counts high) on the plateau: the band is
 * wide there, so the level stays the count's. */
static void c_bias(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    c5 = 98;
    run_s(3600);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR) <= 1.0, "a +15 mV bias on the plateau changes nothing: %.0f pm", drop);
}

/* From the clamp: the count runs unbounded while clamped (no 90.5% floor:
 * codex), then the band. */
static void c_clamp_cross(void) {
    become_full();
    vdd_mv = 3900; c5 = 100;
    run_s(30);
    watch_reset();
    run_s(6 * 3600);
    CHECK(abs((int)battery_level_permille() - (1000 - (int)(6 * PM_PER_HOUR + 0.5))) <= 2,
          "the count through the clamp, ~883: %u", battery_level_permille());
    c5 = 97;
    run_s(1200);
    int hi = (int)battery_curve_pm(battery_pack_mv() + BATTERY_BAND_MV_UP) + BATTERY_BAND_PM;
    CHECK((int)battery_level_permille() <= hi, "inside the band after the clamp: %u (top %d)",
          battery_level_permille(), hi);
    CHECK(w_big == 0 && w_rises == 0, "smooth and never up: %d big, %d rises", w_big, w_rises);
}

/* A reboot on battery: no saved level below the clamp, so the first estimate's
 * curve, then the count. (Its accuracy is the voltage's: not claimed.) */
static void c_reboot(void) {
    c_start(90);
    CHECK(abs((int)battery_level_permille() - (int)battery_curve_pm(battery_pack_mv())) <= 3,
          "started from the curve: %u", battery_level_permille());
    CHECK(battery_count_state() == BATTERY_COUNT_RUN, "and counting: %u", battery_count_state());
}

/* --- Regressions for codex's implementation review ---------------------------- */

/* An allowance reaching the clamp is no upper bound: a count of ~95% with the
 * pack just under the clamp (5C 98, 4019 mV) is not ratcheted down. */
static void c_band_top(void) {
    become_full();
    vdd_mv = 3900; c5 = 100;
    run_s(30);
    run_s(2 * 3600);   /* the count to ~961 */
    uint16_t l0 = battery_level_permille();
    c5 = 98;
    run_s(600);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR / 6) <= 1.0, "no ratchet below the clamp's allowance: %.0f pm in 10 min", drop);
}

/* The exact boundary: an estimate of 4011 mV (eight 97s and two 98s, codex)
 * puts the upward allowance at 4036 mV, the clamp: no bound. */
static int edge_k;
static int tgt_edge(void) { return (edge_k++ % 10) < 8 ? 97 : 98; }
static void c_band_top_edge(void) {
    become_full();
    vdd_mv = 3900; c5 = 100;
    run_s(30);
    run_s(2 * 3600);
    c5 = 0xFF; c5_src = tgt_edge;
    run_s(300);
    CHECK(battery_pack_mv() == 4011, "the estimate at the boundary, 4011 mV: %u", battery_pack_mv());
    CHECK(battery_band_upper() == 1000, "no upper bound there: %d", battery_band_upper());
    uint16_t l0 = battery_level_permille();
    run_s(600);
    double drop = l0 - battery_level_permille();
    CHECK(fabs(drop - PM_PER_HOUR / 6) <= 1.0, "no ratchet at the boundary: %.0f pm in 10 min", drop);
    c5_src = NULL;
}

/* A boot on battery above the cut never shows 0%: 5C 30 is 3424 mV, 4 pm on
 * the curve, shown as the 1% floor. */
static void c_floor_boot(void) {
    c_start(30);
    CHECK(battery_level_permille() == 10, "the floor, not the curve's 4: %u", battery_level_permille());
    CHECK(battery_level_pct() == 1 && !power_lights_cut(), "1%%, no cut: %u", battery_level_pct());
}

/* The cut latching during the relaxation after an unplug: 0 wins over the
 * re-seat, and time left stays hidden. (The cut threshold raised over
 * HC_BATTCFG, as the bench can.) */
static void c_cut_reseat(void) {
    u_target = tgt_m_minus; u_delta = -100;
    model_from(400, u_follow);
    run_s(90);
    u_target = tgt_fixed; tgt_fixed_pm = 400;
    vdd_mv = 3900; chrg_low = false;
    run_s(60);
    uint8_t out[8];
    battery_cfg(1, 0, 3990, out);   /* a cut above the pack: latches in ~30 s */
    run_s(BATTERY_RELAX_S + 120);
    CHECK(power_lights_cut(), "the cut latched");
    CHECK(battery_level_permille() == 0, "0 through the re-seat: %u", battery_level_permille());
    CHECK(battery_time_left_min() == 0xFFFF, "no time left: %u", battery_time_left_min());
    CHECK(battery_count_state() == BATTERY_COUNT_CUT, "state CUT: %u", battery_count_state());
}

/* A held count whose reports go stale counts again (codex: the hold needs
 * fresh evidence). */
static void c_hold_stale(void) {
    c_start(80);
    c5 = 88;
    run_s(120);
    CHECK(battery_count_state() == BATTERY_COUNT_HELD, "held: %u", battery_count_state());
    uint16_t l1 = battery_level_permille();
    c5 = 0xFF;
    run_s(30 * 60);
    double drop = l1 - battery_level_permille();
    /* The estimate expires after C5_STALE_MS (20 s), then the count runs:
     * 29.7 min at SIM_MW is ~9.55 pm (codex: check it closely). */
    double want_st = 29.7 / 60.0 * PM_PER_HOUR;
    CHECK(fabs(drop - want_st) <= 1.5, "counting again once stale: %.0f pm in 30 min, want ~%.2f", drop, want_st);
}

/* After a handover on USB, later idle reports keep the level bounded, not
 * walking to the curve (codex). The pack reads 300 pm above the held level
 * (raised once to the band's edge), then 150 above that for an hour. */
static void c_handover_stays(void) {
    u_target = tgt_m_minus; u_delta = -100;
    model_from(300, u_follow);
    run_s(5 * 60);
    uint16_t held = battery_level_permille();
    u_target = tgt_fixed; tgt_fixed_pm = held + 300;
    chrg_low = false; vdd_mv = 4470;
    run_s(BATTERY_PAUSE_S + 60);
    uint16_t adopted = battery_level_permille();
    tgt_fixed_pm = adopted + 150;
    run_s(3600);
    CHECK(band_ok(battery_level_permille(), adopted), "bounded, not walked to the curve: %u (adopted %u, band ~%d)",
          battery_level_permille(), adopted, band_expect(adopted));
}

/* A level adopted on idle USB enters battery operation floored (codex, verify:
 * a boot on USB at 3424 mV adopted 4 pm and kept showing 0% on the pack). */
static void c_floor_entry(void) {
    vdd_mv = 4470; chrg_low = false; c5 = 30;   /* idle USB, the charger off */
    run_s(30);
    CHECK(battery_level_permille() < 10, "on USB the curve's own 4 pm: %u", battery_level_permille());
    vdd_mv = 3900;
    run_s(5);
    CHECK(battery_level_permille() == 10 && battery_level_pct() == 1, "on the pack, the 1%% floor: %u",
          battery_level_permille());
}

/* A clamped boot with the below-band marker saved restores it as 89%, not the
 * 95% guess: under a light load the count runs below 90% while clamped. */
static void c_clamp_marker(void) {
    kb_eeconfig_set_batt_level(890);
    vdd_mv = 3900; c5 = 100;
    run_s(30);
    CHECK(battery_level_permille() == 890, "the marker restored: %u", battery_level_permille());
}

/* --- The drains, replayed through the firmware at one-second steps ---------- */

/* Each RAM-log entry's LED drive and backlight set the sim's load, so the
 * model sees what the board drew; truth is the time left to the cut, which
 * R3 showed equals the logged energy within 0.1 point at this load. */
static long   cr_t0, cr_t_cut;
static double cr_worst_lo, cr_worst_hi;
static long   cr_n, cr_bad;
static int    cr_row, cr_sec;
static double cr_band[10][3];   /* sum, min, max */
static long   cr_band_n[10];

/* Once a simulated second: the level against the truth at that second. */
static void cr_hook(void) {
    cr_sec++;
    if (battery_supply() != BATTERY_SUPPLY_BATTERY || battery_level_permille() == 0xFFFF) return;
    long t = rp[cr_row].t_s - rp[cr_row].dur_s + cr_sec;
    if (t <= cr_t0 || t >= cr_t_cut) return;
    double truth = 100.0 * (1.0 - (double)(t - cr_t0) / (double)(cr_t_cut - cr_t0));
    double e = battery_level_permille() / 10.0 - truth;
    int b = truth >= 100 ? 9 : (int)(truth / 10);
    cr_band[b][0] += e; cr_band_n[b]++;
    if (e < cr_band[b][1]) cr_band[b][1] = e;
    if (e > cr_band[b][2]) cr_band[b][2] = e;
    if (e < cr_worst_lo) cr_worst_lo = e;
    if (e > cr_worst_hi) cr_worst_hi = e;
    cr_n++;
    if (fabs(e) > 3.0) cr_bad++;
}

static const char *const ORDERS[] = {"the monotone ramp (stress)", "interleaved", "shuffled"};

/* `limit`: the points allowed at every second, everywhere above the cut. */
static void c_replay(const char *what, const char *path, const char *t0, double t0_frac, double hours, int order,
                     double limit) {
    usb_configured = true;   /* both drains ran with USB data attached */
    rp_order = order;
    if (!rp_load(path)) return;
    cr_t0    = rp_epoch(t0);
    cr_t_cut = cr_t0 + (long)(hours * 3600.0 + t0_frac);
    vdd_mv = rp[0].vdd_avg; chrg_low = rp[0].chg_any; c5 = 0xFF;
    run_s(2);
    for (int i = 0; i < 10; i++) { cr_band[i][0] = 0; cr_band[i][1] = 99; cr_band[i][2] = -99; cr_band_n[i] = 0; }
    cr_worst_lo = 99; cr_worst_hi = -99; cr_n = cr_bad = 0;
    rp_second_hook = cr_hook;
    for (int i = 0; i < rp_n; i++) {
        rp_row_t *r = &rp[i];
        if (r->led_pm >= 0) drive_sum = (uint32_t)r->led_pm * (81u * 3u * 255u) / 1000u;   /* the log's per mille is of LED_LOAD_MAX */
        if (r->bkl >= 0) sim_bkl = (uint8_t)r->bkl;
        cr_row = i; cr_sec = 0;
        rp_play(i);
    }
    rp_second_hook = NULL;
    printf("  %s, reports %s: %ld seconds on the pack, the level against the time left:\n", what, ORDERS[order], cr_n);
    for (int b = 9; b >= 0; b--) {
        if (!cr_band_n[b]) continue;
        printf("    %3d-%3d%%  mean %+5.1f  [%+5.1f, %+5.1f]\n", b * 10, b * 10 + 10, cr_band[b][0] / cr_band_n[b],
               cr_band[b][1], cr_band[b][2]);
    }
    printf("    worst %+.1f / %+.1f, %ld seconds outside 3 points\n", cr_worst_lo, cr_worst_hi, cr_bad);
    CHECK(cr_n > 100000, "%s: seconds compared %ld", what, cr_n);
    CHECK(cr_worst_lo >= -limit && cr_worst_hi <= limit, "%s, %s: within %.0f points at every second: worst %+.1f / %+.1f",
          what, ORDERS[order], limit, cr_worst_lo, cr_worst_hi);
}

#define R3_T0 "2026-10-15 23:37", 59.44, 50.39
#define E2_T0 "2026-10-12 11:34", 16.0, 50.39
static void c_replay_r3(const char *p)      { c_replay("R3", p, R3_T0, 1, 3.0); }
static void c_replay_r3_shuf(const char *p) { c_replay("R3", p, R3_T0, 2, 3.0); }
static void c_replay_r3_ramp(const char *p) { c_replay("R3", p, R3_T0, 0, 3.0); }
static void c_replay_2e(const char *p)      { c_replay("2e (to its reboot)", p, E2_T0, 1, 3.0); }
static void c_replay_2e_shuf(const char *p) { c_replay("2e (to its reboot)", p, E2_T0, 2, 3.0); }
static void c_replay_2e_ramp(const char *p) { c_replay("2e (to its reboot)", p, E2_T0, 0, 3.0); }
