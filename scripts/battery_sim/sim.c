/* Host replay of the firmware's battery.c and power.c, verbatim, against a
 * simulated board: VDD through a fake ADC, the charger's CHRG pin, and the
 * CH582F's `5C` reports every 5 s. One scenario per process, because
 * battery.c's state is file-static. Build and run everything with run.sh.
 *
 * What it checks is plans/BATTERY-GAUGE-PLAN.md's Phase 1 behaviour: the
 * supply decision in every state of 1.1's table, the level's ratchet, the
 * top-clamp countdown, charging never claiming 100 before the charger stops,
 * and the low-battery protection. It cannot check the fit or the curve against
 * the pack -- only a meter can. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "quantum.h"
#include "battery.h"
#include "power.h"
#include "kb_eeconfig.h"

struct fake_adc fake_adc;

/* --- The world -------------------------------------------------------------- */
static uint32_t now_ms;
static int      vdd_mv = 3900;       /* 0: the conversion fails */
static int      vdd_dip_mv;          /* every 10th sample reads this much lower */
static bool     chrg_low;
static int      chrg_pulse;          /* >0: CHRG toggles with this period, in ticks */
static uint8_t  c5 = 0xFF;           /* what the module reports; 0xFF = silent */
static uint8_t  module_level = 0xFF; /* its last report, as ch582_get_battery() */
static uint16_t reports;
static uint32_t last_recv;
static bool     seen;
static uint8_t  scale = 255;
static int      n_alerts;
static char     last_alert[32] = "";
static int      failures;

uint32_t timer_read32(void) { return now_ms; }
uint32_t timer_elapsed32(uint32_t last) { return now_ms - last; }
uint32_t last_input_activity_elapsed(void) { return 0; }
bool     gpio_read_pin(int pin) { return pin == CHARGE_CHRG_PIN ? !chrg_low : true; }
bool     rgb_matrix_is_enabled(void) { return true; }
uint8_t  ch582_get_battery(void) { return module_level; }
uint32_t ch582_battery_age_ms(void) { return seen ? now_ms - last_recv : UINT32_MAX; }
uint16_t ch582_battery_reports(void) { return reports; }
bool     ch582_is_usb(void) { return false; }
bool     ch582_is_connected(void) { return true; }
void     display_set_alert(const char *m) { n_alerts++; snprintf(last_alert, sizeof last_alert, "%s", m); }
void     display_set_backlight_cap(uint8_t c) { (void)c; }
uint8_t  display_backlight_effective(void) { return 10; }
uint32_t sn32f2xx_led_load(void) { return scale ? 82u * 3u * 255u / 2u : 0u; }
void     sn32f2xx_set_power_scale(uint8_t s) { scale = s; }

/* The persisted level, as kb_eeconfig keeps it: whole percent + 1, 0 = unset. */
static uint8_t saved_p1;       /* 0.5 % steps + 1, as kb_eeconfig keeps it */
static int     saved_writes;   /* flash writes: the real setter writes only on a change */
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

#define CHECK(cond, ...)                                              \
    do {                                                              \
        if (!(cond)) {                                                \
            failures++;                                               \
            printf("  FAIL line %d (t=%.1f s): ", __LINE__, now_ms / 1000.0); \
            printf(__VA_ARGS__);                                      \
            printf("\n");                                             \
        }                                                             \
    } while (0)

/* The displayed level, watched every tick. */
static uint8_t w_last = 0xFF;
static int     w_rises, w_falls, w_big;
static void watch_reset(void) { w_last = battery_level_pct(); w_rises = w_falls = w_big = 0; }
static void watch(void) {
    uint8_t p = battery_level_pct();
    if (p == 0xFF) return;
    if (w_last != 0xFF && p != w_last) {
        if (p > w_last) w_rises++; else w_falls++;
        if (abs((int)p - (int)w_last) > 1) w_big++;   /* whole percent: one step at a time */
    }
    w_last = p;
}

static unsigned rng = 12345;
static int jitter(void) {   /* -1, 0 or +1, deterministic */
    rng = rng * 1103515245u + 12345u;
    return (int)((rng >> 16) % 3u) - 1;
}
static int c5_jitter;         /* when set, each report carries +-1 of noise */
/* When set, each scheduled report's value comes from here instead of c5 (the
 * charging-model scenarios drive U this way); return > 100 for no report. */
static int (*c5_src)(void);

/* One `5C` frame, as the CH582F driver hands it over. */
static void deliver(uint8_t v) {
    module_level = v;
    reports++;
    last_recv = now_ms;
    seen      = true;
    battery_5c_report(v);
}

static void tick(void) {
    now_ms += 100;
    int mv = vdd_mv;
    if (mv && vdd_dip_mv && (now_ms / 100u) % 10u == 0) mv -= vdd_dip_mv;
    fake_adc.ADB = mv > 0 ? (uint32_t)((2000u * 4096u + (unsigned)mv / 2u) / (unsigned)mv) : 0u;
    if (chrg_pulse) chrg_low = ((now_ms / 100u) % (unsigned)chrg_pulse) < (unsigned)(chrg_pulse / 2 + 1);
    if (c5_src && now_ms % 2500u == 0) {
        int v = c5_src();
        if (v >= 0 && v <= 100) deliver((uint8_t)v);
    } else if (c5 <= 100 && now_ms % 2500u == 0) {   /* ~2.6 s measured on the board */
        /* Jitter is around the true value, and at the top clamp that value is
         * far above 100: a pack at 4.1 V cannot read 99. Only below it. */
        int v = c5 + ((c5_jitter && c5 < 100) ? jitter() : 0);
        deliver((uint8_t)(v < 0 ? 0 : v > 100 ? 100 : v));
    }
    battery_task();
    watch();
}
static void run_s(uint32_t s) { for (uint32_t i = 0; i < s * 10u; i++) tick(); }

static uint32_t ticks_until(battery_supply_t want, uint32_t max) {
    for (uint32_t i = 1; i <= max; i++) {
        tick();
        if (battery_supply() == want) return i;
    }
    return 0xFFFFFFFFu;
}

static const char *state_name(battery_state_t s) {
    static const char *n[] = {"none", "battery", "charging", "full", "usb"};
    return s <= BATTERY_STATE_USB ? n[s] : "?";
}

/* Plugged in with the pack full: the charger has terminated, `5C` clamps. */
static void become_full(void) {
    vdd_mv = 4470; chrg_low = false; c5 = 100;
    run_s(30);
}

/* --- Scenarios ------------------------------------------------------------- */

static void boot_battery(void) {
    vdd_mv = 3900; c5 = 59;
    CHECK(ticks_until(BATTERY_SUPPLY_BATTERY, 20) <= 11, "supply should reach BATTERY within ~1 s");
    CHECK(battery_state() == BATTERY_STATE_BATTERY, "state %s", state_name(battery_state()));
    run_s(20);
    CHECK(battery_5c_rounded() == 59, "median %u", battery_5c_rounded());
    CHECK(battery_pack_mv() >= 3670 && battery_pack_mv() <= 3685, "pack %u mV, want ~3677", battery_pack_mv());
    /* 5C 59 = 3677 mV; the curve between 3640 (80) and 3680 (100):
     * 80 + 37 * 20 / 40 = 98 pm, which shows as 10%. */
    CHECK(battery_level_pct() == 10, "59 -> 3.677 V -> ~10%%, got %u (%u pm)", battery_level_pct(),
          battery_level_permille());
    CHECK(battery_ran_from_pack(), "a board running on battery has a pack");
}

static void boot_battery_clamp(void) {
    vdd_mv = 3900; c5 = 100;
    run_s(20);
    CHECK(battery_level_permille() == 950, "no history at the clamp starts at 950, got %u", battery_level_permille());
    CHECK(battery_level_pct() == 95, "shows 95, got %u", battery_level_pct());
    run_s(3600);
    CHECK(battery_level_pct() == 93 && battery_level_permille() < 950, "counts down: 93 after an hour, got %u (%u pm)",
          battery_level_pct(), battery_level_permille());
}

static void boot_usb_full(void) {
    vdd_mv = 4470; chrg_low = true; c5 = 100;
    run_s(1);   /* the charger starts, sees a full pack, terminates */
    chrg_low = false;
    CHECK(battery_supply() == BATTERY_SUPPLY_EXTERNAL, "USB at 4470 mV is EXTERNAL");
    run_s(30);
    CHECK(battery_state() == BATTERY_STATE_FULL, "state %s", state_name(battery_state()));
    CHECK(battery_level_pct() == 100, "full shows 100, got %u", battery_level_pct());
    CHECK(!battery_ran_from_pack(), "never ran from the pack");
}

/* Full charge, unplug, 5C at 100 for 5.3 h, then falling to 16 at 57.7 h --
 * the 09-25 run's shape -- with +-1 of jitter on every report. */
static void discharge(void) {
    become_full();
    CHECK(battery_level_pct() == 100, "starts full, got %u", battery_level_pct());
    saved_writes = 0;
    vdd_mv = 3900; chrg_low = false; c5_jitter = 1;
    run_s(2);
    watch_reset();
    const uint32_t clamp_s = 19080, end_s = 207720;   /* 5.3 h, 57.7 h */
    for (uint32_t s = 0; s < end_s; s += 5) {
        if (s < clamp_s) {
            c5 = 100;
        } else {
            uint32_t into = s - clamp_s, span = end_s - clamp_s;
            c5 = (uint8_t)(99 - (83u * into) / span);   /* 99 -> 16 */
        }
        if (s == clamp_s - 5) {
            CHECK(battery_level_permille() == 905, "the countdown reaches its 90.5 floor as the clamp exits, got %u pm",
                  battery_level_permille());
        }
        run_s(5);
    }
    CHECK(w_rises == 0, "never rises on battery: %d rises", w_rises);
    CHECK(w_big == 0, "every step is 1%%: %d bigger", w_big);
    CHECK(w_falls >= 95, "falls a percent at a time all the way down: %d falls", w_falls);
    CHECK(battery_level_pct() <= 1, "5C 16 (3.30 V) ends near 0, got %u", battery_level_pct());
    CHECK(saved_writes <= 5, "at most 5 saved-level writes on the way down (the flash blink): %d", saved_writes);
    printf("  %d saved-level writes on the discharge\n", saved_writes);
    printf("  %d display changes over %.1f h, ending at %u%%\n", w_falls, end_s / 3600.0, battery_level_pct());
}

/* The 2026-09-28 charge log, one row a minute: VDD mean with every 10th sample
 * at the minute's minimum, 5C as logged, CHRG low throughout. */
static void charge_log(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("  FAIL cannot open %s\n", path); failures++; return; }
    char line[512];
    int  rows = 0, supply_bad = 0;
    uint8_t max_pct = 0;
    bool started = false;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || strncmp(line, "time", 4) == 0) continue;
        int vavg, vmin, pct, rgb, age, onb, chg;
        char *p = strchr(line, ',');
        if (!p || sscanf(p + 1, "%d,%d,%d,%d,%d,%d,%d", &vavg, &vmin, &pct, &rgb, &age, &onb, &chg) != 7) continue;
        vdd_mv = vavg; vdd_dip_mv = vavg - vmin; c5 = (uint8_t)pct; chrg_low = chg != 0;
        if (!started) { run_s(2); watch_reset(); started = true; }
        for (int s = 0; s < 60; s++) {
            run_s(1);
            if (battery_supply() != BATTERY_SUPPLY_EXTERNAL) supply_bad++;
        }
        if (battery_level_pct() != 0xFF && battery_level_pct() > max_pct) max_pct = battery_level_pct();
        rows++;
    }
    fclose(f);
    CHECK(rows > 400, "replayed %d rows", rows);
    CHECK(supply_bad == 0, "EXTERNAL through the whole charge: %d seconds were not", supply_bad);
    CHECK(battery_state() == BATTERY_STATE_CHARGING, "still charging at the log's end: %s",
          state_name(battery_state()));
    CHECK(w_falls == 0, "never falls while charging: %d falls", w_falls);
    CHECK(w_big == 0, "rises one percent at a time: %d bigger", w_big);
    CHECK(saved_writes == 0, "nothing saved while charging: %d writes", saved_writes);
    CHECK(max_pct <= 97, "never claims 100 before the charger stops: reached %u", max_pct);
    printf("  %d minutes replayed, level at the end %u%% (%u pm)\n", rows, battery_level_pct(),
           battery_level_permille());
    /* The log ends at 10:34; the charge went on in CV until CHRG released at
     * ~12:32. Two more hours at the clamp must still not reach 100. */
    vdd_mv = 4300; vdd_dip_mv = 0; c5 = 100; chrg_low = true;
    run_s(2 * 3600);
    CHECK(battery_state() == BATTERY_STATE_CHARGING, "still charging: %s", state_name(battery_state()));
    CHECK(battery_level_pct() == 97, "97 through the rest of CV, never 100 before termination: %u (%u pm)",
          battery_level_pct(), battery_level_permille());
    /* The charger terminates. */
    chrg_low = false; vdd_mv = 4470; vdd_dip_mv = 0; c5 = 100;
    run_s(30);
    CHECK(battery_state() == BATTERY_STATE_FULL && battery_level_pct() == 100, "termination -> full 100, got %s %u",
          state_name(battery_state()), battery_level_pct());
}

static void transitions(void) {
    vdd_mv = 3900; c5 = 70;
    run_s(20);
    /* Plug in, charging hard. */
    vdd_mv = 4193; chrg_low = true;
    uint32_t t = ticks_until(BATTERY_SUPPLY_EXTERNAL, 50);
    CHECK(t <= 3, "plug-in (CHRG low) seen in %u ticks", t);
    run_s(10);
    /* Unplug. */
    vdd_mv = 3900; chrg_low = false;
    t = ticks_until(BATTERY_SUPPLY_BATTERY, 50);
    CHECK(t <= 20, "unplug seen within 2 s: %u ticks", t);
    /* Plug in, charger idle (a full pack), BT position. */
    vdd_mv = 4470;
    t = ticks_until(BATTERY_SUPPLY_EXTERNAL, 50);
    CHECK(t <= 6, "USB at 4470 seen in %u ticks", t);
    /* The CV taper: VDD wandering through the old 4300 threshold. */
    chrg_low = true;
    int flips = 0;
    for (int i = 0; i < 600; i++) {
        vdd_mv = (i & 1) ? 4310 : 4290;
        tick();
        if (battery_supply() != BATTERY_SUPPLY_EXTERNAL) flips++;
    }
    CHECK(flips == 0, "no flicker through 4300: %d ticks off EXTERNAL", flips);
    /* Terminated, VDD inside the hysteresis band: hold. */
    chrg_low = false;
    for (int i = 0; i < 600; i++) {
        vdd_mv = (i & 1) ? 4150 : 4050;
        tick();
        if (battery_supply() != BATTERY_SUPPLY_EXTERNAL) flips++;
    }
    CHECK(flips == 0, "held inside the 4000-4100 band: %d ticks off EXTERNAL", flips);
    /* Cable position. */
    vdd_mv = 4790;
    run_s(2);
    CHECK(battery_supply() == BATTERY_SUPPLY_EXTERNAL, "cable position is EXTERNAL");
    /* Failed conversions change nothing. */
    vdd_mv = 0;
    run_s(5);
    CHECK(battery_supply() == BATTERY_SUPPLY_EXTERNAL, "failed ADC reads hold the state");
}

static void no_pack(void) {
    vdd_mv = 4470; c5 = 0; chrg_pulse = 5;   /* ~2 Hz */
    run_s(2);
    int off = 0, state_changes = 0;
    battery_state_t last = battery_state();
    for (int i = 0; i < 600; i++) {
        tick();
        if (battery_supply() != BATTERY_SUPPLY_EXTERNAL) off++;
        if (battery_state() != last) state_changes++;
        last = battery_state();
    }
    CHECK(off == 0, "no pack, pulsing CHRG: EXTERNAL throughout (%d ticks off)", off);
    CHECK(state_changes == 0, "state steady under the pulse (%d changes)", state_changes);
    CHECK(!battery_ran_from_pack(), "never ran from a pack");
    CHECK(battery_state() != BATTERY_STATE_FULL, "no pack is never full");
}

static void protection(void) {
    vdd_mv = 3900; c5 = 60;
    run_s(20);
    CHECK(n_alerts == 0 && scale == 255, "healthy pack: no alert, no cut");
    c5 = 30;   /* 3.424 V: under warn (3550), over cut (3400) */
    run_s(70);
    CHECK(n_alerts == 1 && strcmp(last_alert, "Battery low") == 0, "warned once: %d \"%s\"", n_alerts, last_alert);
    CHECK(scale == 255, "not cut above 3400 mV");
    c5 = 27;   /* 3.397 V: under cut */
    run_s(200);   /* a 64-report mean follows a step in ~2.7 min; a real pack moves 1-3 mV in that time */
    CHECK(power_lights_cut() && scale == 0, "cut under 3400 mV");
    c5 = 0xFF; /* the module goes quiet */
    run_s(60);
    CHECK(battery_5c_rounded() == 0xFF, "stale after 20 s");
    CHECK(power_lights_cut(), "stale never clears the cut");
    c5 = 27;
    vdd_mv = 4193; chrg_low = true;   /* plugged in */
    run_s(3);
    CHECK(power_lights_cut(), "still cut after 3 s of USB");
    run_s(4);
    CHECK(!power_lights_cut() && scale == 255, "restored after 5 s of USB");
}

static void critical(void) {
    vdd_mv = 3900; c5 = 90;
    run_s(20);
    /* 5C 90 is 3949 mV: 550 + 4 * 50 / 36 = 555 pm on the curve. High enough that
     * "Low at once" below is a drop, not a level that was already near 0. */
    CHECK(battery_level_pct() >= 50, "starts high: %u", battery_level_pct());
    c5 = 0;
    while (now_ms % 2500u != 0) tick();   /* align: the next report is 2.5 s away */
    run_s(5);
    CHECK(!power_lights_cut(), "two zeroes are not yet critical");
    run_s(3);
    CHECK(power_lights_cut(), "three fresh zeroes cut at once");
    CHECK(battery_level_pct() == 0, "and the panel says Low at once, not 45 min later: %u", battery_level_pct());
}

/* Three zeroes landing between two ticks are three reports, not one. */
static void burst(void) {
    vdd_mv = 3900; c5 = 50;
    run_s(30);
    c5 = 0xFF;          /* no scheduled reports from here */
    deliver(0); deliver(0); deliver(0);
    tick();
    CHECK(power_lights_cut(), "a burst of three zero frames is critical");
}

/* The cut must lift on fresh evidence of USB, never on a remembered EXTERNAL. */
static void restore_needs_evidence(void) {
    vdd_mv = 3900; c5 = 50;
    run_s(20);
    c5 = 0;
    run_s(20);
    CHECK(power_lights_cut(), "cut");
    c5 = 50;
    vdd_mv = 4193; chrg_low = true;   /* plugged in for one second */
    run_s(1);
    vdd_mv = 0; chrg_low = false;     /* unplugged, and the ADC fails */
    run_s(20);
    CHECK(power_lights_cut(), "no fresh evidence of USB: the cut holds");
}

/* A charger fault at the top clamp: CHRG releases, the pack is really at 90. */
static void charger_fault(void) {
    vdd_mv = 4300; chrg_low = true; c5 = 100;
    run_s(120);
    watch_reset();
    vdd_mv = 4470; chrg_low = false; c5 = 90;
    int full_ticks = 0;
    for (int i = 0; i < 600; i++) {
        tick();
        if (battery_state() == BATTERY_STATE_FULL) full_ticks++;
    }
    CHECK(full_ticks == 0, "a fault is never FULL: %d ticks", full_ticks);
    CHECK(w_rises == 0 || battery_level_pct() < 100, "no 100 from a fault");
    CHECK(w_big == 0, "no jump when the charger stops: %d", w_big);
}

/* CHRG drops out for 2 s mid-charge, with a report in the gap. */
static void chrg_gap(void) {
    vdd_mv = 4193; chrg_low = true; c5 = 80;
    run_s(120);
    uint8_t before = battery_level_pct();
    watch_reset();
    chrg_low = false;
    run_s(2);
    chrg_low = true;
    run_s(60);
    CHECK(w_big == 0, "no jump across a CHRG gap: %d", w_big);
    CHECK(battery_level_pct() <= before + 5, "not reinterpreted without the I*R: %u -> %u", before,
          battery_level_pct());
}

/* Booted charging, and the charge climbs fast before the session qualifies. */
static void boot_charging_rise(void) {
    vdd_mv = 4193; chrg_low = true; c5 = 80;
    run_s(20);
    watch_reset();
    c5 = 90;
    run_s(180);
    CHECK(w_big == 0, "one 5%% step at a time: %d bigger", w_big);
}

/* Plugged back in within minutes of a FULL: the pack is full, and the panel
 * keeps saying so through the charger's top-up (a deliberate choice; codex
 * finding 3 asked for a cap, see battery.c level_report). */
static void full_then_replug(void) {
    become_full();
    vdd_mv = 3900; chrg_low = false;
    run_s(30);
    vdd_mv = 4300; chrg_low = true;
    run_s(600);
    CHECK(battery_level_pct() == 100, "a just-full pack topping up shows 100: %u", battery_level_pct());
}

/* The re-seat owed after a real charge survives a brief replug. */
static void reseat_survives_replug(void) {
    vdd_mv = 4193; chrg_low = true; c5 = 80;
    run_s(120);
    vdd_mv = 3900; chrg_low = false; c5 = 70;
    run_s(3);
    vdd_mv = 4193; chrg_low = true; c5 = 80;
    run_s(10);
    vdd_mv = 3900; chrg_low = false; c5 = 70;
    run_s(20);
    /* 5C 70 = 3774 mV; the curve between 3748 (150) and 3785 (200):
     * 150 + 26 * 50 / 37 = 185 pm. */
    CHECK(battery_level_permille() == 185, "re-seated after the brief replug: %u pm", battery_level_permille());
}

/* A threshold above the top clamp cannot be judged there: no cut, no warning. */
static void threshold_at_clamp(void) {
    vdd_mv = 3900; c5 = 100;
    run_s(20);
    uint8_t out[8];
    battery_cfg(1, 4200, 4100, out);
    run_s(120);
    CHECK(!power_lights_cut() && n_alerts == 0, "no cut or warning on a clamp bound");
}

/* Every period closes on time, even through an ADC outage, and not at boot. */
static void log_cadence(void) {
    uint8_t out[29];
    vdd_mv = 3900; c5 = 60;
    run_s(300);
    battery_log_read(0, out);
    CHECK((out[1] | out[2] << 8) == 0, "no entry in the first 5 min (was an instant one at boot)");
    run_s(301);
    battery_log_read(0, out);
    CHECK((out[1] | out[2] << 8) == 1, "one entry at 10 min: %u", out[1] | out[2] << 8);
    CHECK((out[9] | out[10] << 8) == 600, "period 600 s in the reply: %u", out[9] | out[10] << 8);
    CHECK(out[0] == 4, "log v4: %u", out[0]);
    vdd_mv = 0;
    run_s(20 * 60);
    battery_log_read(2, out);
    CHECK((out[1] | out[2] << 8) == 3, "two more entries through a 20 min ADC outage: %u", out[1] | out[2] << 8);
    CHECK((out[13] | out[14] << 8) == 0, "an outage entry says 0 mV, not a stale mean");
    CHECK((out[19] | out[28] << 8) >= 200, "and still counts every 5C report: %u", out[19] | out[28] << 8);
}

/* Plugged in for 20 s mid-discharge: the charge current lifts 5C, but it is not
 * a charging session, so the level must not move. */
static void brief_plug(void) {
    vdd_mv = 3900; c5 = 60;
    run_s(40);
    uint16_t before = battery_level_permille();
    watch_reset();
    vdd_mv = 4193; chrg_low = true; c5 = 72;
    run_s(20);
    vdd_mv = 3900; chrg_low = false; c5 = 60;
    run_s(120);
    CHECK(w_rises == 0, "a 20 s plug-in never raises the level (%d rises)", w_rises);
    CHECK(battery_level_permille() == before, "level unchanged: %u -> %u", before, battery_level_permille());
}

/* Charging for a while, then unplugged mid-charge: the pack relaxes downward and
 * the level eases after it, 1% per 30 s at most. */
static void unplug_mid_charge(void) {
    vdd_mv = 4193; chrg_low = true; c5 = 50;
    run_s(120);
    c5 = 80;
    run_s(120);
    uint16_t charging = battery_level_permille();
    CHECK(charging < 300, "charging at 5C 80 (3.861 V less 150 mV of I*R) is ~12%%, got %u pm", charging);
    vdd_mv = 3900; chrg_low = false; c5 = 70;
    run_s(3);   /* one report after the change, taken on the pack */
    CHECK(battery_5c_rounded() == 0xFF, "no estimate from one report: the charging ones were forgotten");
    run_s(13);
    CHECK(battery_5c_rounded() == 70, "the estimate is post-unplug reports only: %u", battery_5c_rounded());
    /* 5C 70 = 3774 mV: 150 + 26 * 50 / 37 = 185 pm (as reseat_survives_replug). */
    CHECK(battery_level_permille() == 185, "re-seated at the first post-unplug estimate: %u pm",
          battery_level_permille());
    watch_reset();
    run_s(20 * 60);
    CHECK(w_rises == 0, "no rise after the re-seat (%d)", w_rises);
    printf("  charging level %u pm, re-seated on the pack at 185 pm\n", charging);
}

/* A countdown that ran slow: the clamp exits early, and the level eases down to
 * the curve instead of jumping. */
static void countdown_ease(void) {
    become_full();
    vdd_mv = 3900;
    run_s(2);
    watch_reset();
    run_s(3600);   /* one hour at the clamp */
    c5 = 90;       /* 3.949 V: the curve says 550 + 4 * 50 / 36 = 555 pm */
    run_s(20 * 60);
    CHECK(w_rises == 0, "no rise (%d)", w_rises);
    CHECK(w_big == 0, "no jump bigger than one 5%% step (%d)", w_big);
    CHECK(battery_level_pct() <= 80, "has come down to the curve: %u (%u pm)", battery_level_pct(),
          battery_level_permille());
}

/* The median must be built only from reports taken on the current supply,
 * whatever position the ring was left at. Walks every offset of the ring. */
static void ring_restart(void) {
    vdd_mv = 3900; c5 = 60;
    run_s(20);
    for (int k = 0; k < 7; k++) {
        vdd_mv = 4193; chrg_low = true; c5 = 90;
        run_s((uint32_t)(5 * (7 + k)));
        vdd_mv = 3900; chrg_low = false; c5 = 40;
        run_s(1);
        for (int r = 0; r < 7; r++) {
            run_s(5);
            uint8_t m = battery_5c_rounded();
            CHECK(m == 0xFF || m == 40, "offset %d, report %d after unplugging: median %u mixes in the old supply",
                  k, r + 1, m);
        }
    }
}

/* JD's case, 2026-09-28: full on USB, then a cable -> BT slider flip,
 * which reboots the board. It must come back at 100, not the 95 guess. */
static void reboot_after_full(void) {
    saved_p1 = 201;   /* 100%, saved before the reboot */
    vdd_mv = 3900; c5 = 100;
    run_s(20);
    CHECK(battery_level_pct() == 100, "restored to 100 at the clamp, got %u", battery_level_pct());
}

/* A saved level that does not fit the clamp (a pack swapped, say) is ignored. */
static void reboot_saved_mismatch(void) {
    saved_p1 = 81;    /* 40% */
    vdd_mv = 3900; c5 = 100;
    run_s(20);
    CHECK(battery_level_permille() == 950, "a saved 40%% at the clamp is not believed: %u pm", battery_level_permille());
}

/* Below the clamp the voltage is the authority: a saved level is not restored. */
static void reboot_below_clamp(void) {
    saved_p1 = 161;   /* 80% */
    vdd_mv = 3900; c5 = 59;
    run_s(20);
    CHECK(battery_level_pct() == 10, "the curve, not the saved 80%%: %u", battery_level_pct());
}

/* What is saved follows the level. */
static void persist_tracks(void) {
    become_full();
    CHECK(saved_p1 == 201, "full is saved as 100%%: p1 %u", saved_p1);
    vdd_mv = 3900; chrg_low = false;
    run_s(3 * 3600);   /* the countdown: 1000 - 10800 / 184 = ~942 pm */
    CHECK(saved_p1 == 186, "saved as 92.5%% (rounded down to the step): p1 %u", saved_p1);
}

/* E2: "Battery low" fires once per discharge, whatever the voltage does, and
 * re-arms only after a real charging session (or a new threshold). 5C 55 is
 * 3642 mV, under the 3680 warning and over the 3400 cut; 62 is 3704 mV and 75
 * is 3818 mV, past where the old rule (warn + 100 mV) re-armed it. */
static void warn_once(void) {
    vdd_mv = 3900; c5 = 70;
    run_s(30);
    c5 = 55;
    run_s(200);
    CHECK(n_alerts == 1 && strcmp(last_alert, "Battery low") == 0, "warned once: %d \"%s\"", n_alerts, last_alert);
    for (int k = 0; k < 3; k++) {
        c5 = 75; run_s(200);
        c5 = 55; run_s(200);
    }
    CHECK(n_alerts == 1, "repeated crossings on battery do not re-fire it: %d alerts", n_alerts);
}

static void warn_brief_plug(void) {
    vdd_mv = 3900; c5 = 55;
    run_s(200);
    CHECK(n_alerts == 1, "warned: %d", n_alerts);
    vdd_mv = 4193; chrg_low = true; c5 = 68;     /* a dump: 40 s on USB, charging */
    run_s(40);
    vdd_mv = 3900; chrg_low = false; c5 = 55;
    run_s(300);
    CHECK(n_alerts == 1, "a brief plug-in does not re-arm it (10-01 01:06): %d alerts", n_alerts);
}

static void warn_after_charge(void) {
    vdd_mv = 3900; c5 = 55;
    run_s(200);
    CHECK(n_alerts == 1, "warned: %d", n_alerts);
    vdd_mv = 4193; chrg_low = true; c5 = 70;     /* a real charge, 20 min */
    run_s(20 * 60);
    vdd_mv = 3900; chrg_low = false; c5 = 62;    /* on the pack, above the warning */
    run_s(300);
    CHECK(n_alerts == 1, "nothing above the threshold: %d alerts", n_alerts);
    c5 = 55;                                     /* the next crossing */
    run_s(200);
    CHECK(n_alerts == 2 && strcmp(last_alert, "Battery low") == 0, "re-fires after a real charge: %d \"%s\"",
          n_alerts, last_alert);
}

static void warn_cfg_rearms(void) {
    vdd_mv = 3900; c5 = 55;
    run_s(200);
    CHECK(n_alerts == 1, "warned: %d", n_alerts);
    uint8_t out[8];
    battery_cfg(1, 3700, 3400, out);
    run_s(60);
    CHECK(n_alerts == 2, "a new threshold over HC_BATTCFG re-arms it: %d alerts", n_alerts);
}

/* --- The replay adapter (Phase 1b, B2) ------------------------------------------
 * Replays a battery log in either format ak820battery.py writes:
 *   one-minute (the 09-28 charge, pre-gauge firmware): one module_pct value a
 *     minute and the flags at the minute's end;
 *   v3/v4, ten-minute: every 5C report of the period as c5_mean, c5_n, c5_min,
 *     c5_max; flags at the period's end (on_batt, charging, ...) AND OR-ed over
 *     it (flags_any), kept apart.
 * Each interval's length comes from consecutive timestamps, never assumed.
 * What a log does not hold is reconstructed, and every reconstruction is
 * printed with a [synthetic] label:
 *   - the reports inside a v3/v4 interval: c5_n of them, evenly spaced, on a
 *     monotone ramp from the logged min to the logged max whose sum matches
 *     the logged mean (rp_values); ascending when the mean rose from the
 *     previous interval, descending when it fell (the order inside a period
 *     is not logged);
 *   - a charger change inside an interval (the end state differs from the
 *     OR-ed flags, or from the previous end): at the interval's middle;
 *   - the one-minute format's single value: a report every 2.5 s at it.
 * The opening of a v3/v4 charge from flat is therefore the plan's Note 1
 * reconstruction (ascending from the logged min of 0), and the 09-28 log's
 * first minute is its logged 4, with no zero invented. */
#define RP_MAX 1024
typedef struct {
    char     time[20];
    long     t_s;          /* seconds since the epoch of the file's first row */
    int      dur_s;
    int      vdd_avg, vdd_min;
    bool     v34;          /* the ten-minute formats */
    double   c5_mean;
    int      c5_n, c5_min, c5_max, c5_single;
    int      level_pm;     /* the logged level, per mille, -1 if none */
    bool     chg_end, chg_any, ext_end;
    /* what the replay showed at the interval's end */
    uint16_t r_level;
    uint8_t  r_state;
} rp_row_t;
static rp_row_t rp[RP_MAX];
static int      rp_n;
static void   (*rp_second_hook)(void);   /* called once a simulated second during a replay */
static int      rp_synth_lines;
static int      rp_writes_before_full;   /* saved-level writes before the first FULL */
static bool     rp_seen_full;

static void rp_label(const char *fmt, const char *time, double a, double b) {
    if (rp_synth_lines++ < 6) {
        printf("  [synthetic] %s: ", time);
        printf(fmt, a, b);
        printf("\n");
    }
}

static long rp_epoch(const char *t) {   /* "YYYY-MM-DD HH:MM", days from a fixed month */
    int y, mo, d, h, mi;
    if (sscanf(t, "%d-%d-%d %d:%d", &y, &mo, &d, &h, &mi) != 5) return -1;
    static const int cum[] = {0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334};
    long days = (long)y * 365 + y / 4 + cum[mo - 1] + d;
    return ((days * 24 + h) * 60 + mi) * 60;
}

static int rp_col(char **cols, int n, const char *name) {
    for (int i = 0; i < n; i++) if (!strcmp(cols[i], name)) return i;
    return -1;
}

static int rp_split(char *line, char **cols, int max) {
    int n = 0;
    line[strcspn(line, "\r\n")] = 0;
    for (char *p = line; n < max;) {
        cols[n++] = p;
        char *c = strchr(p, ',');
        if (!c) break;
        *c = 0;
        p = c + 1;
    }
    return n;
}

static bool rp_load(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { printf("  FAIL cannot open %s\n", path); failures++; return false; }
    char line[1024], hdr[1024];
    char *h[40], *c[40];
    if (!fgets(hdr, sizeof hdr, f)) { fclose(f); return false; }
    int hn = rp_split(hdr, h, 40);
    int i_t = rp_col(h, hn, "time"), i_va = rp_col(h, hn, "vdd_avg"), i_vm = rp_col(h, hn, "vdd_min");
    int i_mean = rp_col(h, hn, "c5_mean"), i_n = rp_col(h, hn, "c5_n"), i_mn = rp_col(h, hn, "c5_min"),
        i_mx = rp_col(h, hn, "c5_max"), i_lvl = rp_col(h, hn, "level"), i_pct = rp_col(h, hn, "module_pct"),
        i_chg = rp_col(h, hn, "charging"), i_ext = rp_col(h, hn, "external"), i_any = rp_col(h, hn, "flags_any");
    bool v34 = i_mean >= 0;
    rp_n = 0;
    while (fgets(line, sizeof line, f) && rp_n < RP_MAX) {
        if (line[0] == '#') continue;
        int n = rp_split(line, c, 40);
        if (n < hn) continue;
        rp_row_t *r = &rp[rp_n];
        memset(r, 0, sizeof *r);
        snprintf(r->time, sizeof r->time, "%s", c[i_t]);
        r->t_s = rp_epoch(c[i_t]);
        r->vdd_avg = atoi(c[i_va]); r->vdd_min = atoi(c[i_vm]);
        r->v34 = v34;
        r->chg_end = atoi(c[i_chg]) != 0;
        r->level_pm = -1;
        if (v34) {
            r->c5_n = atoi(c[i_n]);
            r->c5_mean = c[i_mean][0] ? atof(c[i_mean]) : -1.0;
            r->c5_min = c[i_mn][0] ? atoi(c[i_mn]) : -1;
            r->c5_max = c[i_mx][0] ? atoi(c[i_mx]) : -1;
            r->chg_any = strstr(c[i_any], "charging") != NULL;
            r->ext_end = atoi(c[i_ext]) != 0;
            if (c[i_lvl][0]) r->level_pm = (int)(atof(c[i_lvl]) * 10.0 + 0.5);
        } else {
            r->c5_single = atoi(c[i_pct]);
            r->chg_any = r->chg_end;
            r->ext_end = true;
        }
        rp_n++;
    }
    fclose(f);
    /* Durations from the timestamps; the first row takes the next row's. */
    for (int i = 1; i < rp_n; i++) rp[i].dur_s = (int)(rp[i].t_s - rp[i - 1].t_s);
    if (rp_n > 1) rp[0].dur_s = rp[1].dur_s;
    const char *base = strrchr(path, '/');
    printf("  %s: %d rows, %s format, %d s intervals\n", base ? base + 1 : path, rp_n,
           v34 ? "ten-minute (v3/v4)" : "one-minute", rp_n ? rp[0].dur_s : 0);
    return rp_n > 0;
}

/* c5_n report values: a monotone ramp from the logged min to the logged max,
 * bent (v = min + (max - min) * x^g, x from 0 to 1) so its mean is the logged
 * mean, then nudged by single counts so the sum matches it exactly. A ramp,
 * not a constant at the mean: inside a charging interval the reports climb,
 * and the estimate at its end is near the max, not the mean. */
#define RP_VALS_MAX 4096   /* a 10-minute period has held at most 344 reports */
static int rp_values(const rp_row_t *r, bool ascending, uint8_t *v) {
    int n = r->c5_n;
    if (n <= 0 || r->c5_mean < 0) return 0;
    CHECK(n <= RP_VALS_MAX, "%s: %d reports in one interval, more than the reconstruction holds", r->time, n);
    if (n > RP_VALS_MAX) return 0;
    int  lo = r->c5_min, hi = r->c5_max;
    long sum = lround(r->c5_mean * n);
    if (n == 1 || lo == hi) {
        /* One report, or every report equal: the only reconstruction there is,
         * and it must still match the logged mean (codex, gate 2 check). */
        for (int i = 0; i < n; i++) v[i] = (uint8_t)lo;
        CHECK(lo == hi && sum == (long)lo * n, "%s: %d report(s) at %d cannot make sum %ld (max %d)", r->time, n, lo,
              sum, hi);
        return n;
    }
    double target = (double)sum / n, glo = 1e-3, ghi = 1e3, g = 1.0;
    for (int it = 0; it < 100; it++) {          /* the mean falls as g rises */
        g = sqrt(glo * ghi);
        double m = 0;
        for (int i = 0; i < n; i++) m += lo + (hi - lo) * pow((double)i / (n - 1), g);
        if (m / n > target) glo = g; else ghi = g;
    }
    long have = 0;
    for (int i = 0; i < n; i++) {
        v[i] = (uint8_t)lround(lo + (hi - lo) * pow((double)i / (n - 1), g));
        have += v[i];
    }
    /* Nudge interior values one count at a time, keeping the ramp monotone,
     * sweeping until the sum is exact or a whole sweep changes nothing. A
     * deficit is filled from the top down, a surplus taken from the bottom up,
     * so each sweep makes room for the next. */
    while (have != sum) {
        bool moved = false;
        if (have < sum) {
            for (int i = n - 2; i >= 1 && have < sum; i--)
                if (v[i] < v[i + 1]) { v[i]++; have++; moved = true; }
        } else {
            for (int i = 1; i <= n - 2 && have > sum; i++)
                if (v[i] > v[i - 1]) { v[i]--; have--; moved = true; }
        }
        if (!moved) break;
    }
    /* What the reconstruction promises, checked rather than assumed (codex). */
    bool mono = true;
    for (int i = 1; i < n; i++) if (v[i] < v[i - 1]) mono = false;
    CHECK(have == sum && v[0] == lo && v[n - 1] == hi && mono,
          "%s: reconstruction: sum %ld of %ld, ends %u/%u of %d/%d, monotone %d", r->time, have, sum, v[0],
          v[n - 1], lo, hi, mono);
    if (!ascending) for (int i = 0; i < n / 2; i++) { uint8_t t = v[i]; v[i] = v[n - 1 - i]; v[n - 1 - i] = t; }
    return n;
}

/* Play one interval: VDD, CHRG (moved at the middle if it changed inside),
 * and the reports, evenly spaced. */
static void rp_play(int i) {
    rp_row_t *r = &rp[i];
    static uint8_t vals[RP_VALS_MAX];
    vdd_mv = r->vdd_avg; vdd_dip_mv = r->vdd_avg - r->vdd_min;
    bool prev_chg = i ? rp[i - 1].chg_end : r->chg_any;
    bool chg_first = r->chg_any && (prev_chg || !r->chg_end) ? true : r->chg_end;
    bool chg_second = r->chg_end;
    if (r->v34 && r->chg_any && !r->chg_end) rp_label("CHRG released at the interval's middle", r->time, 0, 0);
    if (r->v34 && r->chg_end && i && !prev_chg) {
        chg_first = false;
        rp_label("CHRG low from the interval's middle", r->time, 0, 0);
    }
    int ticks = r->dur_s * 10;
    if (!r->v34) {
        c5 = (uint8_t)r->c5_single; chrg_low = r->chg_end;
        for (int t = 0; t < ticks; t++) {
            tick();
            if (rp_second_hook && t % 10 == 9) rp_second_hook();
        }
    } else {
        c5 = 0xFF;   /* reports come only from the schedule below */
        bool asc = !i || rp[i - 1].c5_mean < 0 || r->c5_mean >= rp[i - 1].c5_mean;
        int n = rp_values(r, asc, vals);
        if (i == 0 && n)
            rp_label("first interval: %.0f reports from %.0f, ascending (the plan's Note 1 opening)", r->time, n,
                     r->c5_min);
        int next = 0;
        for (int t = 0; t < ticks; t++) {
            chrg_low = (t < ticks / 2) ? chg_first : chg_second;
            while (next < n && (long)(next * 2 + 1) * ticks / (2L * n) <= t) deliver(vals[next++]);
            tick();
            if (rp_second_hook && t % 10 == 9) rp_second_hook();
        }
    }
    r->r_level = battery_level_permille();
    r->r_state = (uint8_t)battery_state();
    if (r->r_state != BATTERY_STATE_FULL && !rp_seen_full) rp_writes_before_full = saved_writes;
    if (r->r_state == BATTERY_STATE_FULL) rp_seen_full = true;
}

/* Replays a whole log; returns the seconds not on EXTERNAL. Watches every step. */
static int rp_run(const char *path) {
    if (!rp_load(path)) return -1;
    int off = 0;
    /* The board booted into the first row's world (on USB for a charge),
     * not into the default 3900 mV: that would be a second on the pack. */
    vdd_mv = rp[0].vdd_avg; chrg_low = rp[0].chg_any; c5 = 0xFF;
    run_s(2);
    watch_reset();
    for (int i = 0; i < rp_n; i++) {
        rp_play(i);
        if (battery_supply() != BATTERY_SUPPLY_EXTERNAL) off++;
    }
    if (rp_synth_lines > 6) printf("  [synthetic] ... %d reconstructions in all\n", rp_synth_lines);
    return off;
}

/* The first interval whose every report sat at the clamp. */
static int rp_first_clamped(void) {
    for (int i = 0; i < rp_n; i++)
        if ((rp[i].v34 && rp[i].c5_min == 100) || (!rp[i].v34 && rp[i].c5_single == 100)) return i;
    return -1;
}

static void rp_table(int every) {
    printf("  %-16s %7s %9s %8s\n", "entry end", "5C", "replayed", "logged");
    for (int i = 0; i < rp_n; i++) {
        if (i % every && i != rp_n - 1) continue;
        double m = rp[i].v34 ? rp[i].c5_mean : rp[i].c5_single;
        printf("  %-16s %7.2f %7.1f %% ", rp[i].time, m, rp[i].r_level == 0xFFFF ? -1.0 : rp[i].r_level / 10.0);
        if (rp[i].level_pm >= 0) printf("%6.1f %%\n", rp[i].level_pm / 10.0); else printf("%8s\n", "-");
    }
}

/* What TODAY's charging logic does with each recorded charge from flat: the
 * baseline Phase 1b's model is compared with. It reads low below the clamp
 * (curve(V - 150 mV) on the fitted discharge curve), then races to 90.5 at
 * 0.4 %/min once 5C clamps, creeps to the 97.0 cap, and says 100 only at the
 * charger's termination. */
static void baseline_common(const char *what, int off, uint8_t max_before_full) {
    CHECK(off == 0, "%s: EXTERNAL throughout: %d intervals were not", what, off);
    CHECK(w_falls == 0, "%s: never falls while charging: %d falls", what, w_falls);
    CHECK(max_before_full <= 97, "%s: never past 97 before the charger stops: %u", what, max_before_full);
    CHECK(rp_writes_before_full == 0, "%s: nothing saved while charging: %d writes", what, rp_writes_before_full);
}

static uint8_t rp_max_before_full(void) {
    uint16_t m = 0;
    for (int i = 0; i < rp_n; i++)
        if (rp[i].r_state != BATTERY_STATE_FULL && rp[i].r_level != 0xFFFF && rp[i].r_level > m) m = rp[i].r_level;
    return (uint8_t)((m + 5u) / 10u);
}

/* 09-28 charge, one-minute log, 03:02 -> 10:34. Its end is before the
 * termination (~12:32, readings.csv): a [synthetic] tail of 2 h at the clamp,
 * then CHRG released. */
static void baseline_0928(const char *path) {
    int off = rp_run(path);
    if (off < 0) return;
    rp_table(60);
    CHECK(w_big == 0, "09-28: rises one percent at a time: %d bigger", w_big);
    baseline_common("09-28", off, rp_max_before_full());
    int k = rp_first_clamped();
    printf("  5C first clamped: %s (%.2f h in); level then %.1f %%\n", rp[k].time,
           (rp[k].t_s - rp[0].t_s + rp[0].dur_s) / 3600.0, rp[k].r_level / 10.0);
    printf("  [synthetic] tail: 2 h at the clamp, charging, then CHRG released (termination ~12:32)\n");
    vdd_mv = 4300; vdd_dip_mv = 0; c5 = 100; chrg_low = true;
    run_s(2 * 3600);
    CHECK(battery_level_permille() == 970, "09-28: at the 97.0 cap before termination: %u pm", battery_level_permille());
    chrg_low = false; vdd_mv = 4470;
    run_s(30);
    CHECK(battery_state() == BATTERY_STATE_FULL && battery_level_pct() == 100, "09-28: 100 at termination: %s %u",
          state_name(battery_state()), battery_level_pct());
}

/* 10-01 charge, ten-minute log, boot ~08:46 -> 19:46, termination in the 18:16
 * entry. Logged on deef6053dd (the PLACEHOLDER curve), so its logged levels are
 * not today's and are shown, not compared. */
static void baseline_1001(const char *path) {
    int off = rp_run(path);
    if (off < 0) return;
    rp_table(3);
    baseline_common("10-01", off, rp_max_before_full());
    CHECK(w_big <= 1, "10-01: one percent at a time, but for the FULL step: %d bigger", w_big);
    /* The last interval below the clamp, 12:36: mean 98.03 -> 4019 mV under
     * charge; less 150 mV is 3869 mV, which the curve puts at 450 + 1 * 50 / 28
     * = 451 pm. The level, which only rises, is near that: it reads low. */
    int k = rp_first_clamped();
    const rp_row_t *b = &rp[k - 2];
    printf("  the last interval below the clamp, %s: level %.1f %% (curve(4019 - 150 mV) = 45.1 %%)\n", b->time,
           b->r_level / 10.0);
    CHECK(b->r_level >= 430 && b->r_level <= 460, "10-01: reads ~45%% at 12:36, 3.8 h into a charge from flat: %u pm",
          b->r_level);
    int full_at = -1, cap_at = -1;
    for (int i = 0; i < rp_n; i++) {
        if (cap_at < 0 && rp[i].r_level == 970) cap_at = i;
        if (full_at < 0 && rp[i].r_state == BATTERY_STATE_FULL) full_at = i;
    }
    CHECK(full_at >= 0 && rp[full_at].r_level == 1000, "10-01: 100 at termination");
    CHECK(cap_at >= 0 && cap_at < full_at, "10-01: reaches the 97 cap before termination");
    if (cap_at >= 0 && full_at >= 0)
        printf("  at the 97 cap from %s; FULL at %s: %.1f h at the cap, then a 3-point step\n", rp[cap_at].time,
               rp[full_at].time, (rp[full_at].t_s - rp[cap_at].t_s) / 3600.0);
}

/* 10-04 charge, ten-minute log, boot ~20:02 -> 21:42 (the preservation dump; the
 * rest of that boot was lost to the bootloader). */
static void baseline_1004a(const char *path) {
    int off = rp_run(path);
    if (off < 0) return;
    rp_table(1);
    baseline_common("10-04", off, rp_max_before_full());
    CHECK(w_big == 0, "10-04: one percent at a time: %d bigger", w_big);
    /* A number, not "unknown", from the third interval on (the first estimate
     * comes in the first, the session qualifies at 60 s), and the endpoint
     * where today's logic puts it. Tolerance +-10 pm: the self-check lands the
     * reconstruction within +5 pm of the log on the firmware that wrote it,
     * and the refitted curve moves curve(V - 150) by under 5 pm here. */
    int unknown = 0;
    for (int i = 2; i < rp_n; i++) if (rp[i].r_level == 0xFFFF) unknown++;
    CHECK(rp_n == 10 && unknown == 0, "10-04: numeric from 20:32 on: %d unknown of %d", unknown, rp_n - 2);
    CHECK(rp[rp_n - 1].r_level >= 171 && rp[rp_n - 1].r_level <= 191,
          "10-04: ~18.1%% at 21:42 (+-10 pm): %u pm", rp[rp_n - 1].r_level);
}

/* The adapter checked against the firmware that WROTE the log: run.sh builds
 * this one scenario against 759e265796's battery.c, which logged the 10-04
 * charge. The replay must land on the logged level in every interval (the log
 * floors to 0.5 %). It cannot be exact: the order and timing of the reports
 * inside an interval are reconstructed. */
static void replay_selfcheck(const char *path) {
    int off = rp_run(path);
    if (off < 0) return;
    int worst = 0, n = 0;
    for (int i = 0; i < rp_n; i++) {
        if (rp[i].level_pm < 0 || rp[i].r_level == 0xFFFF) continue;
        int got = (rp[i].r_level / 5) * 5;
        int d = got - rp[i].level_pm;
        if (abs(d) > abs(worst)) worst = d;
        n++;
    }
    rp_table(1);
    printf("  replayed vs logged: %d intervals, worst %+d pm\n", n, worst);
    CHECK(n == rp_n, "every interval compared: %d of %d", n, rp_n);
    CHECK(abs(worst) <= 10, "the replay lands within 1 point of the logged level: worst %+d pm", worst);
}

#if BATTERY_LOG_VERSION >= 5
#include "model.c"   /* Phase 1b, B2: the charging model's scenarios (flash 2) */
#endif

static void stale(void) {
    vdd_mv = 3900; c5 = 60;
    run_s(40);
    uint8_t before = battery_level_pct();
    c5 = 0xFF;
    run_s(25);
    CHECK(battery_5c_rounded() == 0xFF, "stale after 20 s");
    CHECK(battery_level_pct() == before, "level holds while stale: %u -> %u", before, battery_level_pct());
    c5 = 60;
    run_s(20);
    CHECK(battery_5c_rounded() == 60, "recovers: median %u", battery_5c_rounded());
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: sim SCENARIO [charge-log.csv]\n");
        return 2;
    }
    battery_init();
    const char *s = argv[1];
    if      (!strcmp(s, "boot_battery"))       boot_battery();
    else if (!strcmp(s, "boot_battery_clamp")) boot_battery_clamp();
    else if (!strcmp(s, "boot_usb_full"))      boot_usb_full();
    else if (!strcmp(s, "discharge"))          discharge();
    else if (!strcmp(s, "charge_log"))         charge_log(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "transitions"))        transitions();
    else if (!strcmp(s, "no_pack"))            no_pack();
    else if (!strcmp(s, "protection"))         protection();
    else if (!strcmp(s, "critical"))           critical();
    else if (!strcmp(s, "brief_plug"))         brief_plug();
    else if (!strcmp(s, "unplug_mid_charge"))  unplug_mid_charge();
    else if (!strcmp(s, "countdown_ease"))     countdown_ease();
    else if (!strcmp(s, "stale"))              stale();
    else if (!strcmp(s, "ring_restart"))       ring_restart();
    else if (!strcmp(s, "burst"))              burst();
    else if (!strcmp(s, "restore_needs_evidence")) restore_needs_evidence();
    else if (!strcmp(s, "charger_fault"))      charger_fault();
    else if (!strcmp(s, "chrg_gap"))           chrg_gap();
    else if (!strcmp(s, "boot_charging_rise")) boot_charging_rise();
    else if (!strcmp(s, "full_then_replug"))   full_then_replug();
    else if (!strcmp(s, "reseat_survives_replug")) reseat_survives_replug();
    else if (!strcmp(s, "threshold_at_clamp")) threshold_at_clamp();
    else if (!strcmp(s, "log_cadence"))        log_cadence();
    else if (!strcmp(s, "reboot_after_full"))  reboot_after_full();
    else if (!strcmp(s, "reboot_saved_mismatch")) reboot_saved_mismatch();
    else if (!strcmp(s, "reboot_below_clamp")) reboot_below_clamp();
    else if (!strcmp(s, "persist_tracks"))     persist_tracks();
    else if (!strcmp(s, "warn_once"))          warn_once();
    else if (!strcmp(s, "warn_brief_plug"))    warn_brief_plug();
    else if (!strcmp(s, "warn_after_charge"))  warn_after_charge();
    else if (!strcmp(s, "warn_cfg_rearms"))    warn_cfg_rearms();
#if BATTERY_LOG_VERSION >= 5
    else if (!strcmp(s, "m_flat_boundary"))       m_flat_boundary();
    else if (!strcmp(s, "m_flat_boundary_above")) m_flat_boundary_above();
    else if (!strcmp(s, "m_unknown_start"))       m_unknown_start();
    else if (!strcmp(s, "m_partial_below_knee"))  m_partial_below_knee();
    else if (!strcmp(s, "m_early_clamp"))         m_early_clamp();
    else if (!strcmp(s, "m_topup_near_full"))     m_topup_near_full();
    else if (!strcmp(s, "m_just_full"))           m_just_full();
    else if (!strcmp(s, "m_delayed_termination")) m_delayed_termination();
    else if (!strcmp(s, "m_delayed_unplug"))      m_delayed_unplug();
    else if (!strcmp(s, "m_log_v5"))              m_log_v5();
    else if (!strcmp(s, "m_log_saturated"))       m_log_saturated();
    else if (!strcmp(s, "m_ceil_hold30")) m_ceil_hold30();
    else if (!strcmp(s, "m_ceil_60_29")) m_ceil_60_29();
    else if (!strcmp(s, "m_ceil_60_30")) m_ceil_60_30();
    else if (!strcmp(s, "m_ceil_clamp_hold")) m_ceil_clamp_hold();
    else if (!strcmp(s, "m_ceil_clamp_entry")) m_ceil_clamp_entry();
    else if (!strcmp(s, "m_ceil_clamp_exit")) m_ceil_clamp_exit();
    else if (!strcmp(s, "m_reports_lost_9")) m_reports_lost_9();
    else if (!strcmp(s, "m_reports_lost_10")) m_reports_lost_10();
    else if (!strcmp(s, "m_pause_short")) m_pause_short();
    else if (!strcmp(s, "m_pause_before")) m_pause_before();
    else if (!strcmp(s, "m_pause_after")) m_pause_after();
    else if (!strcmp(s, "m_pause_relaxing")) m_pause_relaxing();
    else if (!strcmp(s, "m_pause_missing")) m_pause_missing();
    else if (!strcmp(s, "m_pause_from_lost")) m_pause_from_lost();
    else if (!strcmp(s, "m_pause_from_unknown")) m_pause_from_unknown();
    else if (!strcmp(s, "m_pause_then_unplug")) m_pause_then_unplug();
    else if (!strcmp(s, "m_slow_charge")) m_slow_charge();
    else if (!strcmp(s, "m_reseat_up")) m_reseat_up();
    else if (!strcmp(s, "m_reseat_down")) m_reseat_down();
    else if (!strcmp(s, "m_reseat_clamp")) m_reseat_clamp();
    else if (!strcmp(s, "m_reseat_unknown")) m_reseat_unknown();
    else if (!strcmp(s, "m_reseat_lost")) m_reseat_lost();
    else if (!strcmp(s, "m_reseat_missing")) m_reseat_missing();
    else if (!strcmp(s, "m_reseat_replugs")) m_reseat_replugs();
    else if (!strcmp(s, "m_reseat_0929")) m_reseat_0929();
    else if (!strcmp(s, "m_full_fault")) m_full_fault();
    else if (!strcmp(s, "m_replay_0928"))  m_replay_0928(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "m_replay_1001"))  m_replay_1001(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "m_replay_1004a")) m_replay_1004a(argc > 2 ? argv[2] : "");
#endif
    else if (!strcmp(s, "baseline_0928"))      baseline_0928(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "baseline_1001"))      baseline_1001(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "baseline_1004a"))     baseline_1004a(argc > 2 ? argv[2] : "");
    else if (!strcmp(s, "replay_selfcheck"))   replay_selfcheck(argc > 2 ? argv[2] : "");
    else { fprintf(stderr, "unknown scenario %s\n", s); return 2; }
    printf("%s %s\n", failures ? "FAIL" : "ok  ", s);
    return failures ? 1 : 0;
}
