/* Deep sleep's hand-over to the gauge and the log (battery.c's
 * battery_sleep_*; plans/DEEP-SLEEP-BUILD-PLAN.md, sections 4 and 6),
 * #included by sim.c after count.c. A sleep here is what sleep.c does: the
 * hand-over before the lock, QMK's timer standing still (now_ms does not move,
 * no report arrives: the board polls the module for them), the wake, a few
 * awake passes, then the accounting with the slept ms. The sim's awake load is
 * count.c's SIM_MW; asleep it is BATTERY_P_SLEEP_UW. */

#define SLEEP_MW (BATTERY_P_SLEEP_UW / 1000.0)

/* A sleep of `ms`, accounted after `gap_ms` of awake passes (the recovery's
 * first steps: the waking input, then the PCF's read). */
static void sleep_for(uint32_t ms, uint32_t gap_ms) {
    battery_sleep_enter();
    battery_sleep_wake();
    for (uint32_t t = 0; t < gap_ms; t += 100u) tick();
    battery_sleep_account(ms);
}

/* A night: the energy into e_used and the level, never into the average. */
static void s_energy(void) {
    c_start(96);
    run_s(3600);
    uint16_t l0 = battery_level_permille();
    uint32_t e0 = battery_energy_used_mwh_x10();
    uint16_t m0 = battery_avg_minutes();
    uint32_t a0 = battery_power_avg_uw();
    sleep_for(16u * 3600000u, 300);
    double   want_e = SLEEP_MW * 16.0 * 10.0;   /* 0.1 mWh: 13.35 mW for 16 h */
    uint32_t de     = battery_energy_used_mwh_x10() - e0;
    CHECK(fabs(de - want_e) <= 2.0, "16 h asleep is %.0f x 0.1 mWh: %u", want_e, de);
    double drop = l0 - battery_level_permille();
    double want = SLEEP_MW * 16.0 * 1000.0 / 15579.0;   /* pm */
    CHECK(fabs(drop - want) <= 1.0, "the level down %.1f pm for the night: %.0f", want, drop);
    CHECK(battery_avg_minutes() == m0, "the average's minutes unchanged: %u -> %u", m0, battery_avg_minutes());
    CHECK(battery_power_avg_uw() == a0, "the average unchanged: %u -> %u", a0, battery_power_avg_uw());
}

/* Time left is hours of use: across a night it moves only by the level, and
 * at once, not at the next minute. */
static void s_time_left(void) {
    c_start(96);
    run_s(2 * 3600);
    uint16_t t0 = battery_time_left_min(), l0 = battery_level_permille();
    sleep_for(16u * 3600000u, 300);
    uint16_t t1 = battery_time_left_min(), l1 = battery_level_permille();
    /* One pm is ~3 min of time left here, and t0 is up to a minute old (the
     * level moved since it was computed): two pm's worth. */
    double want = (double)t0 * l1 / l0, tol = 2.0 * t0 / l0 + 1.0;
    CHECK(fabs(t1 - want) <= tol, "time left scales with the level only: %u -> %u (want %.0f +- %.0f)", t0, t1,
          want, tol);
    CHECK(t1 < t0, "and it moved at the wake: %u -> %u", t0, t1);
}

/* The floor and the cut hold across a sleep; an unknown level stays unknown. */
static void s_floor_cut(void) {
    c_start(40);   /* 3515 mV: ~28 pm */
    sleep_for(30u * 24u * 3600000u, 300);   /* a month asleep: far past the floor */
    CHECK(battery_level_permille() == 10, "the count stops at 1%%: %u", battery_level_permille());
    c5 = 3;
    run_s(300);
    CHECK(power_lights_cut() && battery_level_permille() == 0, "the cut: 0 (%u)", battery_level_permille());
    sleep_for(3600000u, 300);
    CHECK(battery_level_permille() == 0 && battery_count_state() == BATTERY_COUNT_CUT,
          "still 0 and CUT after a sleep: %u, state %u", battery_level_permille(), battery_count_state());
}

static void s_unknown(void) {
    vdd_mv = 3900; c5 = 0xFF;   /* on battery, the module silent: no estimate, no level */
    run_s(30);
    CHECK(battery_level_permille() == 0xFFFF, "unknown before: %u", battery_level_permille());
    uint32_t e0 = battery_energy_used_mwh_x10();
    sleep_for(3600000u, 300);
    CHECK(battery_level_permille() == 0xFFFF, "still unknown: %u", battery_level_permille());
    CHECK(battery_energy_used_mwh_x10() - e0 >= 133, "the energy still counted: %u",
          battery_energy_used_mwh_x10() - e0);
}

/* A count held below the band before the sleep: the hold is stale after it
 * (the estimate was forgotten), so the sleep's energy is taken. */
static void s_band_hold(void) {
    c_start(80);
    c5 = 88;
    run_s(120);
    CHECK(battery_count_state() == BATTERY_COUNT_HELD, "held before: %u", battery_count_state());
    uint16_t l0 = battery_level_permille();
    sleep_for(16u * 3600000u, 300);
    double drop = l0 - battery_level_permille();
    CHECK(drop >= SLEEP_MW * 16.0 * 1000.0 / 15579.0 - 1.0, "the night taken despite the old hold: %.0f pm", drop);
}

/* Many short sleeps and one long one take the same energy: the remainder
 * below a pm carries. */
static void s_remainder(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    for (int k = 0; k < 2000; k++) sleep_for(28800u, 0);   /* 2000 x 28.8 s = 16 h */
    double drop = l0 - battery_level_permille();
    double want = SLEEP_MW * 16.0 * 1000.0 / 15579.0;
    CHECK(fabs(drop - want) <= 1.0, "2000 short sleeps = one night: %.0f pm (want %.1f)", drop, want);
}

/* The relaxation after an unplug is physical: a sleep ages it. UNKNOWN-CHG at
 * the clamp, unplugged: the re-seat (950) comes RELAX_S after, then needs
 * fresh reports (model.c, m_reseat_unknown). */
static void s_relax(void) {
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(120);
    vdd_mv = 3900; chrg_low = false;
    run_s(60);
    CHECK(battery_level_permille() != 950, "not re-seated a minute after the unplug: %u", battery_level_permille());
    sleep_for(40u * 60000u, 300);   /* longer than RELAX_S */
    run_s(40);
    CHECK(battery_level_permille() == 950, "re-seated 40 s after a 40 min sleep: %u", battery_level_permille());
}

/* --- The log ------------------------------------------------------------------ */

typedef struct { unsigned slept, e_x10, c5_n, level, led, bkl, flags; } lent_t;
static unsigned log_count(void) {
    uint8_t out[29];
    battery_log_read(0, out);
    return out[1] | out[2] << 8;
}
static lent_t log_entry(unsigned idx) {
    uint8_t out[29];
    battery_log_read((uint16_t)idx, out);
    const uint8_t *e = &out[11];
    lent_t r = {(unsigned)(e[0] | e[1] << 8), (unsigned)(e[2] | e[3] << 8), (unsigned)(e[6] | e[15] << 8),
                e[11], (unsigned)(e[12] | e[13] << 8), e[14], e[9]};
    return r;
}
static uint32_t log_since(void) {
    uint8_t out[29];
    battery_log_read(0, out);
    return (uint32_t)out[5] | (uint32_t)out[6] << 8 | (uint32_t)out[7] << 16 | (uint32_t)out[8] << 24;
}

/* Tick until the log holds `n` entries (at most `max_s`): a report delivered
 * on the closing tick lands in the period it closes (sim.c's tick delivers
 * before battery_task), so right after it the closed entries hold every
 * report so far (codex, deep-sleep build review 9: conservation, exactly). */
static bool run_until_entries(unsigned n, uint32_t max_s) {
    for (uint32_t i = 0; i < max_s * 10u; i++) {
        if (log_count() >= n) return true;
        tick();
    }
    return log_count() >= n;
}
static unsigned log_reports(unsigned from, unsigned to) {
    unsigned sum = 0;
    for (unsigned k = from; k < to; k++) sum += log_entry(k).c5_n;
    return sum;
}

/* The log starts at the first tick: now_ms 100, so its periods end at
 * 900,100 + k x 900,000 in log time. */
#define P0_END 900100u

/* A sleep inside one period: no entry until the period's end, then one with
 * the sleep's seconds and energy in it. */
static void s_log_within(void) {
    c_start(96);              /* now 30,000 */
    run_s(200);               /* 230,000 */
    sleep_for(300000u, 200);  /* 5 min asleep, 0.2 s of recovery: log time 530,200 */
    CHECK(log_count() == 0, "no entry yet: %u", log_count());
    CHECK(run_until_entries(1, 380), "one entry at the period's end: %u", log_count());
    lent_t e = log_entry(0);
    CHECK(e.slept == 300, "300 s slept in it: %u", e.slept);
    /* 600 s awake at SIM_MW + 300 s asleep, to a tenth of a mWh and its carry */
    double want = (SIM_MW * 600.0 + SLEEP_MW * 300.0) / 3600.0 * 10.0;
    CHECK(fabs(e.e_x10 - want) <= 1.5, "its energy, the sleep's included: %u x 0.1 mWh (want %.1f)", e.e_x10, want);
    CHECK(e.c5_n == reports, "and every report, exactly: %u of %u", e.c5_n, reports);
}

/* A night across many periods, starting mid-period. */
static void s_log_across(void) {
    c_start(96);                     /* 30,000 */
    run_s(570);                      /* 600,000 */
    uint32_t e0 = battery_energy_used_mwh_x10();
    unsigned r_sleep = reports;
    sleep_for(16u * 3600000u, 300);  /* asleep 600,000 .. 58,200,000; accounted at 58,200,300 */
    unsigned r_live = reports - r_sleep;   /* the recovery's 0.3 s */
    /* Boundaries through now: 900,100 + k x 900,000 <= 58,200,300: k = 0..63, 64 entries */
    CHECK(log_count() == 64, "64 periods closed: %u", log_count());
    lent_t first = log_entry(0);
    CHECK(first.slept == 300, "the first keeps its frozen contents and 300 s slept: %u", first.slept);
    CHECK(first.c5_n == r_sleep, "its reports from before the sleep, exactly: %u of %u", first.c5_n, r_sleep);
    unsigned slept = 0, e_sum = 0, bad = 0;
    for (unsigned k = 0; k < 64; k++) {
        lent_t e = log_entry(k);
        slept += e.slept;
        e_sum += e.e_x10;
        if (k > 0 && (e.slept != 900 || e.c5_n != 0 || e.led != 0 || e.bkl != 0)) bad++;
        if (k > 0 && e.level > log_entry(k - 1).level) bad++;   /* never rises asleep */
    }
    CHECK(bad == 0, "every later entry slept whole, dark, no reports, the level falling: %u bad", bad);
    /* 300 + 63 x 900 = 57,000 s of the 57,600 slept; the last 600 in the open period */
    CHECK(slept == 57000, "57,000 s slept in the closed entries: %u", slept);
    /* the closed entries' energy: 600 s awake before (in the first) + 57,000 s asleep */
    double want = (SIM_MW * 600.0 + SLEEP_MW * 57000.0) / 3600.0 * 10.0;
    /* Within 2: the count's first second (energy_tick's start) and the open
     * carry. Without the carry 64 entries would lose up to 64. */
    CHECK(fabs(e_sum - want) <= 2.0, "their energy %u x 0.1 mWh (want %.1f): the carry kept", e_sum, want);
    CHECK(battery_energy_used_mwh_x10() - e0 >= (unsigned)(SLEEP_MW * 16 * 10 - 2), "e_used the whole night");
    /* Dating: the newest entry ended at 57,600,100 in log time; now is 58,200,300. */
    CHECK(log_since() == 58200300u - 57600100u, "the newest entry's age in log time: %u", log_since());
    run_s(10);
    CHECK(log_count() == 64, "no extra entry after the wake: %u", log_count());
    /* The open period (57,600,100 .. 58,500,100): the sleep's last 600 s,
     * then the awake rest; its reports are the live ones and after. */
    CHECK(run_until_entries(65, 300), "the open period closes: %u", log_count());
    lent_t open = log_entry(64);
    CHECK(open.slept == 600, "the sleep's last 600 s in the open period: %u", open.slept);
    double want_open = (SLEEP_MW * 600.0 + SIM_MW * 300.0) / 3600.0 * 10.0;
    CHECK(fabs(open.e_x10 - want_open) <= 1.5, "its energy %u x 0.1 mWh (want %.1f)", open.e_x10, want_open);
    CHECK(open.c5_n == reports - r_sleep && r_live <= open.c5_n, "its reports, the live ones included: %u of %u",
          open.c5_n, reports - r_sleep);
    CHECK(log_reports(0, 65) == reports, "every report in exactly one entry: %u of %u", log_reports(0, 65), reports);
}

/* A sleep that reaches the floor early: each closed entry's level is the
 * level before the sleep less the sleep's energy up to its end, stopping at
 * the floor -- not a line to the floor across the whole sleep (codex,
 * deep-sleep build review 6). ~28 pm at 13.35 mW reaches 1% in ~21 h. */
static void s_log_floor(void) {
    c_start(40);                     /* 30,000; ~28 pm */
    uint16_t l0 = battery_level_permille();
    sleep_for(3u * 24u * 3600000u, 300);   /* asleep from log time ~30,000 for 72 h */
    unsigned n = log_count(), bad = 0, at_floor = 0;
    double pm_j = 15579.0 * 3.6 / 1000.0;   /* J per pm: E_CAP_MWH's thousandth */
    for (unsigned k = 0; k < n; k++) {
        double t_s  = ((double)P0_END + k * 900000.0 - 30000.0) / 1000.0;
        double want = l0 - SLEEP_MW * t_s / 1000.0 / pm_j;
        if (want < 10.0) want = 10.0;
        int    got  = (int)log_entry(k).level * 5;   /* the log's 0.5% units */
        /* The remainder before the sleep is under a pm; the log keeps 5 pm steps. */
        if (got > want + 1.0 || got < want - 6.0) bad++;
        if (got == 10) at_floor++;
    }
    CHECK(n == 288, "72 h of entries: %u", n);
    CHECK(bad == 0, "every entry's level on the sleep's own debit: %u off (from %u pm)", bad, l0);
    CHECK(at_floor >= 288 - 100, "at the floor from ~21 h on: %u entries", at_floor);
}

/* A cut during the recovery, before the accounting (codex, the deep-sleep
 * build's verify): the night's entries keep the level the sleep began at,
 * debited by the sleep, not the cut's 0. */
static void s_log_late_cut(void) {
    c_start(96);                     /* 30,000; ~689 pm */
    run_s(570);                      /* 600,000 */
    uint16_t l0 = battery_level_permille();
    battery_sleep_enter();
    battery_sleep_wake();
    c5 = 3;                          /* the pack at the cut, reported after the wake */
    unsigned waited = 0;
    while (!power_lights_cut() && waited < 600) { run_s(1); waited++; }
    CHECK(power_lights_cut() && battery_level_permille() == 0, "the cut before the accounting: %u after %u s",
          battery_level_permille(), waited);
    battery_sleep_account(16u * 3600000u);
    unsigned n = log_count(), bad = 0;
    double pm_j = 15579.0 * 3.6 / 1000.0;
    for (unsigned k = 0; k < n && k < 60; k++) {
        double t_s  = ((double)P0_END + k * 900000.0 - 600000.0) / 1000.0;
        double want = l0 - SLEEP_MW * t_s / 1000.0 / pm_j;
        int    got  = (int)log_entry(k).level * 5;
        if (got > want + 1.0 || got < want - 6.0) bad++;
    }
    CHECK(n >= 60, "the night's entries: %u", n);
    CHECK(bad == 0, "the night's levels from %u pm, not the cut's 0: %u off (entry 10: %u)", l0, bad,
          log_entry(10).level * 5);
}

/* A v7 entry partly asleep (codex, deep-sleep build review 9): 600 s awake
 * then 300 s asleep. The awake part matures the average 10 minutes, and the
 * entry costs the awake draw for 600 s plus the sleep's for 300. */
static void s_replay_mixed(void) {
    char path[] = "/tmp/battery_sim_v7m_XXXXXX";
    int fd = mkstemp(path);
    FILE *f = fd >= 0 ? fdopen(fd, "w") : NULL;
    if (!f) { CHECK(0, "cannot write a temp CSV"); return; }
    fprintf(f, "time,slept_s,e_mwh,c5_mean,c5_n,c5_min,c5_max,pack_mv,level,led_pm,bkl,charging,external,flags_any\n");
    for (int k = 0; k < 12; k++) {
        int slept = k >= 4 ? 300 : 0, mins = k * 15;
        fprintf(f, "2026-10-20 %02d:%02d,%d,0.0,96.00,%d,96,96,,,1000,10,0,0,on_batt\n", mins / 60, mins % 60, slept,
                slept ? 240 : 360);
    }
    fclose(f);
    if (!rp_load(path)) { remove(path); return; }
    remove(path);
    vdd_mv = 3900; chrg_low = false; c5 = 0xFF;
    run_s(2);
    for (int i = 0; i < 4; i++) rp_play(i);   /* awake: the draw at these settings */
    uint32_t p_awake = battery_power_uw();
    uint16_t m0 = battery_avg_minutes();
    uint32_t e0 = battery_energy_used_mwh_x10();
    for (int i = 4; i < 12; i++) rp_play(i);
    CHECK(battery_avg_minutes() - m0 == 80, "8 mixed entries matured 80 minutes: %u", battery_avg_minutes() - m0);
    double want = ((double)p_awake * 600.0 + BATTERY_P_SLEEP_UW * 300.0) * 8.0 / 360000.0;   /* uJ to 0.1 mWh */
    double got  = battery_energy_used_mwh_x10() - e0;
    CHECK(fabs(got - want) <= 3.0, "their energy %.0f x 0.1 mWh (want %.1f: %u uW awake for 600 s, asleep 300)",
          got, want, p_awake);
}

/* A sleep longer than the log: its last SIM_LOG_LEN entries, all slept (720;
 * 712 in the devfault build, run.sh's AK820_DEVFAULT pass). */
#ifndef SIM_LOG_LEN
#    define SIM_LOG_LEN 720u
#endif
static void s_log_long(void) {
    c_start(96);
    sleep_for(8u * 24u * 3600000u, 300);
    CHECK(log_count() == SIM_LOG_LEN, "the log full: %u", log_count());
    unsigned bad = 0;
    for (unsigned k = 0; k < SIM_LOG_LEN; k++) if (log_entry(k).slept != 900) bad++;
    CHECK(bad == 0, "every entry slept whole: %u not", bad);
}

/* Between the wake and the accounting: HC_BATTLOG pending, no period closes
 * even past its end, and the reports arriving go to the live period. */
static void s_log_pending(void) {
    c_start(96);
    run_s(860);                      /* 890,000 */
    battery_sleep_enter();
    battery_sleep_wake();
    unsigned r_wake = reports;
    uint8_t out[29];
    battery_log_read(0, out);
    CHECK(out[0] == BATTERY_LOG_PENDING, "pending after the wake: %u", out[0]);
    run_s(20);                       /* 910,000: past the period's end on awake time alone */
    CHECK(log_count() == 0, "no period closed before the accounting: %u", log_count());
    battery_sleep_account(5000u);
    battery_log_read(0, out);
    CHECK(out[0] == BATTERY_LOG_VERSION, "the version back: %u", out[0]);
    CHECK(log_count() == 1, "one entry once accounted: %u", log_count());
    lent_t e = log_entry(0);
    CHECK(e.slept == 5, "5 s slept in it: %u", e.slept);
    CHECK(e.c5_n == r_wake, "the frozen period holds exactly the reports before the wake: %u of %u", e.c5_n, r_wake);
    CHECK(run_until_entries(2, 920), "the next period closes: %u", log_count());
    lent_t e2 = log_entry(1);
    CHECK(e2.c5_n == reports - r_wake && reports - r_wake > 300,
          "the 20 s of live reports in the next period, with the rest: %u of %u", e2.c5_n, reports - r_wake);
}

/* Codex's case (deep-sleep verify 3): the period ends at 900 s; the sleep runs
 * 890-899; the accounting comes at 901. The period ending at 900 keeps its
 * frozen contents and 9 s slept; the live 899-901 goes to the next. */
static void s_log_recovery_boundary(void) {
    c_start(96);                     /* 30,000 */
    run_s(860);                      /* 890,000; log time 890,000 */
    unsigned frozen_reports = 0;
    battery_sleep_enter();
    battery_sleep_wake();
    run_s(2);                        /* the recovery: log time after the account 890,000 + 9,000 + 2,000 */
    battery_sleep_account(9000u);
    CHECK(log_count() == 1, "the period ending at 900,100 closed: %u", log_count());
    lent_t e = log_entry(0);
    frozen_reports = e.c5_n;
    CHECK(e.slept == 9, "with the 9 s slept: %u", e.slept);
    CHECK(frozen_reports >= 340, "and its frozen reports: %u", frozen_reports);
    run_s(900);
    lent_t e2 = log_entry(1);
    CHECK(e2.slept == 0, "the next period slept none: %u", e2.slept);
}

/* Asleep on USB power (the bench, or a charge wake): no energy, the seconds. */
static void s_usb(void) {
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(120);
    uint32_t e0 = battery_energy_used_mwh_x10();
    sleep_for(3600000u, 300);
    CHECK(battery_energy_used_mwh_x10() == e0, "no energy for a sleep on USB: %u",
          battery_energy_used_mwh_x10() - e0);
}

/* Codex (the power-mode icons' review, 7): a sleep on USB power after the
 * RELAX branch banked whole pm at the floor and a charge then raised the
 * level. The night's entries keep the level at the sleep, the sleep costs
 * nothing; with sleep_level_at's p_uw == 0 guard removed they would show
 * the banked remainder debited. From a flat boot (FROM-FLAT, the model near
 * 0), a short charge, an unplug onto the floor for 1500 s (RELAX banks ~7
 * pm at the floor: under RELAX_S, so no re-seat yet), a replug (a MODEL
 * session from the floor: the model path raises the level and never rebases
 * the count), 15 min of charge, then 2 h asleep on USB. */
static int usb_flat_src(void) { static int i; return i++ < 5 ? 10 : 12; }
static void s_usb_relax_banked(void) {
    vdd_mv = 4193; chrg_low = true;
    run_s(2);
    c5_src = usb_flat_src;
    run_s(120);
    unsigned st0 = battery_chg_state(), l_chg = battery_level_permille();
    vdd_mv = 3900; chrg_low = false; c5_src = NULL; c5 = 30;   /* ~3423 mV: above the 3400 mV cut */
    run_s(1500);
    unsigned l_floor = battery_level_permille(), cs = battery_count_state();
    vdd_mv = 4193; chrg_low = true; c5 = 50;   /* under charge; the model rises from the floor, bounded by it */
    run_s(900);
    uint16_t l0 = battery_level_permille();
    uint32_t e0 = battery_energy_used_mwh_x10();
    CHECK(l_floor == 10 && cs == BATTERY_COUNT_RELAX, "at the floor, relaxing, before the replug: %u pm, state %u "
          "(charged from %u pm, state %u)", l_floor, cs, l_chg, st0);
    CHECK(l0 != 0xFFFF && l0 >= 20, "the charge raised the level, known: %u pm", l0);
    unsigned n0 = log_count();
    sleep_for(2u * 3600000u, 300);
    CHECK(battery_energy_used_mwh_x10() == e0, "the sleep on USB cost nothing: %u", battery_energy_used_mwh_x10() - e0);
    unsigned n = log_count(), bad = 0;
    for (unsigned k = n0 + 1; k < n; k++)   /* the entries the sleep laid in, after the frozen one */
        if (log_entry(k).slept == 900 && log_entry(k).level != l0 / 5u) bad++;
    CHECK(n >= n0 + 7, "the sleep's entries: %u", n - n0);
    CHECK(bad == 0, "every slept entry at the level of the sleep, %u pm: %u not", l0, bad);
}

/* An accounting with no wake before it does nothing. */
static void s_no_wake(void) {
    c_start(96);
    uint16_t l0 = battery_level_permille();
    battery_sleep_account(3600000u);
    CHECK(battery_level_permille() == l0, "no wake, no debit: %u -> %u", l0, battery_level_permille());
    CHECK(!battery_sleep_pending(), "nothing pending");
}

/* A v7 log replayed with its sleeps (codex, the deep-sleep review 16): two
 * awake hours at 5C 96, a 16 h night as 64 slept entries, two awake hours.
 * The replay plays each entry's awake part, then its slept part through the
 * hand-over, so the night costs its sleep energy and never matures the
 * average. A CSV with no vdd_avg column takes the supply from the flags. */
static void s_replay_v7(void) {
    char path[] = "/tmp/battery_sim_v7_XXXXXX";
    int fd = mkstemp(path);
    FILE *f = fd >= 0 ? fdopen(fd, "w") : NULL;
    if (!f) { CHECK(0, "cannot write a temp CSV"); return; }
    fprintf(f, "time,slept_s,e_mwh,c5_mean,c5_n,c5_min,c5_max,pack_mv,level,led_pm,bkl,charging,external,flags_any\n");
    int row = 0;
    for (int k = 0; k < 8 + 64 + 8; k++, row++) {
        int slept = (k >= 8 && k < 72) ? 900 : 0;
        int mins = row * 15;
        fprintf(f, "2026-10-20 %02d:%02d,%d,0.0,%s,%d,%s,%s,,,%s,%s,0,0,on_batt\n", (mins / 60) % 24, mins % 60,
                slept, slept ? "" : "96.00", slept ? 0 : 360, slept ? "" : "96", slept ? "" : "96",
                slept ? "0" : "1000", slept ? "0" : "10");
    }
    fclose(f);
    /* rp_epoch wraps the hour at 24: rows past midnight would go backwards, so
     * the durations are fixed here after the load instead. */
    if (!rp_load(path)) { remove(path); return; }
    remove(path);
    for (int i = 0; i < rp_n; i++) rp[i].dur_s = 900;
    vdd_mv = 3900; chrg_low = false; c5 = 0xFF;
    run_s(2);
    for (int i = 0; i < 8; i++) rp_play(i);
    uint16_t l0 = battery_level_permille();
    uint16_t m0 = battery_avg_minutes();
    for (int i = 8; i < 72; i++) rp_play(i);
    CHECK(battery_avg_minutes() == m0, "the night matured nothing: %u -> %u minutes", m0, battery_avg_minutes());
    double drop = l0 - battery_level_permille();
    double want = SLEEP_MW * 16.0 * 1000.0 / 15579.0;
    CHECK(fabs(drop - want) <= 1.5, "the night cost its sleep energy: %.0f pm (want %.1f)", drop, want);
    CHECK(battery_supply() == BATTERY_SUPPLY_BATTERY, "on battery from the flags, no vdd_avg column");
}
