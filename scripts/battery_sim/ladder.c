/* Phase 2's power modes (power.c; plans/PHASE2-BUILD-PLAN.md, section 4, with
 * plans/POWER-MODES-REVISION-PLAN.md's timings and Power saver's ceiling),
 * #included by sim.c when power.h has the modes. One scenario per process, as
 * the rest: power.c's state is file-static too. */

rgb_t rgb_matrix_hsv_to_rgb(hsv_t hsv);   /* power.c's override of QMK's weak hook */

/* The overlay's names: POWER_HAS_BULB's (plans/POWER-MODE-ICONS-PLAN.md), or
 * the ones before them, so the scenarios run against either power.c. */
#ifdef POWER_HAS_BULB
#define NAME_FULL    "Always on"
#define NAME_NORMAL  "Balanced"
#define NAME_SAVER   "Power saver"
#define NAME_MINIMAL "Lights out"
#else
#define NAME_FULL    "Full power"
#define NAME_NORMAL  "Normal power"
#define NAME_SAVER   "Power saver"
#define NAME_MINIMAL "Minimal mode"
#endif

static void ltick(void) {
    tick();
    power_task();
}
static void lrun_s(uint32_t s) { for (uint32_t i = 0; i < s * 10u; i++) ltick(); }

/* On the pack at ~37% (5C 80, ~3.86 V): above the low-battery cap. */
static void on_battery_mid(void) {
    vdd_mv = 3900; c5 = 80;
    lrun_s(30);
}

static void expect_stage(power_stage_t st, uint8_t want_scale, uint8_t want_cap, uint8_t want_val, const char *what) {
    CHECK(power_stage() == st, "%s: stage %d, want %d", what, power_stage(), st);
    CHECK(scale == want_scale, "%s: driver scale %u, want %u", what, scale, want_scale);
    CHECK(bkl_cap == want_cap, "%s: backlight cap %u, want %u", what, bkl_cap, want_cap);
    CHECK(power_val_cap() == want_val, "%s: value cap %u, want %u", what, power_val_cap(), want_val);
}

/* A change of what power.c applies repaints once (apply()'s one
 * rgb_matrix_reinit_effect), and the ticks after it touch nothing: no
 * repaint and no apply() at all (the driver's scale is set only there). */
static void expect_one_repaint(int r0, const char *what) {
    CHECK(rgb_restarts - r0 == 1, "%s: %d repaints, want 1", what, rgb_restarts - r0);
    int r1 = rgb_restarts, s1 = scale_sets;
    lrun_s(2);
    CHECK(rgb_restarts == r1 && scale_sets == s1, "%s: then %d repaints and %d applies, want none", what,
          rgb_restarts - r1, scale_sets - s1);
}

/* No mode's ladder reaches LIGHTS_OFF: its RGB-off time is its screen-off
 * time, so stage_for() returns SCREEN_OFF first. Only the bench holds it. */
static void sweep_no_lights_off(const char *what) {
    power_mode_t m0 = power_mode();
    for (unsigned k = 0; k < POWER_MODE_COUNT; k++, power_cycle_mode()) {
        for (uint32_t t = 0; t <= 1500000u; t += 500u) {
            idle_ms = t; ltick();
            if (power_stage() == POWER_STAGE_LIGHTS_OFF) {
                CHECK(false, "%s, mode %d: LIGHTS_OFF at %u ms idle", what, power_mode(), t);
                break;
            }
        }
    }
    CHECK(power_mode() == m0, "the sweep cycles back to mode %d, got %d", m0, power_mode());
    idle_ms = 0; ltick();
}

/* Normal's stages at their times, each edge at t - 1 ms and t: the dim at
 * 10 min, dark at 20 with no LIGHTS_OFF between, and a keypress restoring all
 * of it within one 10 Hz tick. */
static void l_normal(void) {
    power_init();
    on_battery_mid();
    CHECK(power_mode() == POWER_MODE_NORMAL, "the default is Normal, got %d", power_mode());
    idle_ms = 599999;  ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "599.999 s idle");
    int r0 = rgb_restarts;
    idle_ms = 600000;  ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "10 min idle");
    expect_one_repaint(r0, "Normal's dim");
    idle_ms = 1199999; ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "1199.999 s idle");
    idle_ms = 1200000; ltick(); expect_stage(POWER_STAGE_SCREEN_OFF, 0, 0, 255, "20 min idle");
    idle_ms = 0;       ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "a keypress");
}

/* Power Saver's, and Full never; Fn+B's cycle order and its persistence. */
static void l_modes(void) {
    power_init();
    on_battery_mid();
    power_cycle_mode();
    CHECK(power_mode() == POWER_MODE_SAVER, "Normal -> Saver, got %d", power_mode());
    CHECK(!strcmp(last_status, NAME_SAVER), "overlay '%s'", last_status);
    uint8_t m = 0xFF;
    CHECK(kb_eeconfig_get_power_mode(&m) && m == POWER_MODE_SAVER, "persisted %u", m);
    idle_ms = 0;      ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver, typing");
    idle_ms = 59999;  ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver, 59.999 s");
    int r0 = rgb_restarts;
    idle_ms = 60000;  ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "Saver, 1 min");
    expect_one_repaint(r0, "Saver's dim");   /* its 128 for ACTIVE is not the 64 applied */
    idle_ms = 179999; ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "Saver, 179.999 s");
    idle_ms = 180000; ltick(); expect_stage(POWER_STAGE_SCREEN_OFF, 0, 0, 255, "Saver, 3 min");
    power_cycle_mode();
    CHECK(power_mode() == POWER_MODE_MINIMAL, "Saver -> Minimal, got %d", power_mode());
    CHECK(!strcmp(last_status, NAME_MINIMAL), "overlay '%s'", last_status);
    power_cycle_mode();
    CHECK(power_mode() == POWER_MODE_FULL, "Minimal -> Full, got %d", power_mode());
    idle_ms = 86400000u; ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Full, a day idle");
    power_cycle_mode();
    CHECK(power_mode() == POWER_MODE_NORMAL, "Full -> Normal, got %d", power_mode());
#ifdef POWER_HAS_BULB
    /* Above the low cap the bulb is the mode's own. */
    for (unsigned k = 0; k < POWER_MODE_COUNT; k++, power_cycle_mode())
        CHECK(power_lights_mode() == power_mode(), "mid level, mode %d: bulb %d", power_mode(), power_lights_mode());
#endif
}

/* On USB every mode is Full Power. */
static void l_usb(void) {
    power_init();
    become_full();
    idle_ms = 86400000u;
    lrun_s(2);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "on USB, a day idle");
}

/* Below 15% the lighting follows Saver whatever the mode, its ceiling while
 * typing included, and says so once; Full Power included. */
static void l_low_cap(void) {
    power_init();
    vdd_mv = 3900; c5 = 62;   /* ~3.70 V: ~11% on the curve */
    lrun_s(30);
    CHECK(battery_level_permille() <= 150, "level %u pm, want <= 150", battery_level_permille());
    CHECK(!strcmp(last_status, "Saving power"), "overlay '%s'", last_status);
    last_status[0] = 0;
    idle_ms = 0;     ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "low, Normal, typing");
    idle_ms = 59999; ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "low, Normal, 59.999 s");
    idle_ms = 60000; ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "low, Normal, 1 min");
    CHECK(last_status[0] == 0, "said once, then '%s'", last_status);
#ifdef POWER_HAS_BULB
    /* The bulb says whose stages the lights follow: Saver's for the two
     * lighter modes, Lights out its own. Four presses come back to Normal. */
    static const power_mode_t bulb_low[POWER_MODE_COUNT] = {
        [POWER_MODE_FULL] = POWER_MODE_SAVER, [POWER_MODE_NORMAL] = POWER_MODE_SAVER,
        [POWER_MODE_SAVER] = POWER_MODE_SAVER, [POWER_MODE_MINIMAL] = POWER_MODE_MINIMAL};
    for (unsigned k = 0; k < POWER_MODE_COUNT; k++, power_cycle_mode())
        CHECK(power_lights_mode() == bulb_low[power_mode()], "low, mode %d: bulb %d", power_mode(), power_lights_mode());
#endif
    power_cycle_mode(); power_cycle_mode(); power_cycle_mode();   /* Normal -> Saver -> Minimal -> Full */
    CHECK(power_mode() == POWER_MODE_FULL, "mode %d", power_mode());
    idle_ms = 0;      ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "low, Full, typing");
    idle_ms = 120000; ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "low, Full, 2 min");
    idle_ms = 180000; ltick(); expect_stage(POWER_STAGE_SCREEN_OFF, 0, 0, 255, "low, Full, 3 min");
    sweep_no_lights_off("low");
}

/* The dim is a ceiling on the value: it never raises one, and it keeps hue.
 * So is Power saver's while typing. (colour.c checks both through QMK's real
 * conversion.) */
static void l_val_cap(void) {
    power_init();
    on_battery_mid();
    idle_ms = 600000; ltick();
    hsv_t hi = {191, 255, 200}, lo = {191, 255, 30};
    rgb_t a = rgb_matrix_hsv_to_rgb(hi), b = rgb_matrix_hsv_to_rgb(lo);
    CHECK(a.r == 64, "200 capped to 64, got %u", a.r);
    CHECK(b.r == 30, "30 left alone, got %u", b.r);
    idle_ms = 0; ltick();
    a = rgb_matrix_hsv_to_rgb(hi);
    CHECK(a.r == 200, "after the wake 200, got %u", a.r);
    power_cycle_mode(); ltick();   /* Saver, typing */
    a = rgb_matrix_hsv_to_rgb(hi); b = rgb_matrix_hsv_to_rgb(lo);
    CHECK(a.r == 128, "Saver: 200 capped to 128, got %u", a.r);
    CHECK(b.r == 30, "Saver: 30 left alone, got %u", b.r);
}

/* The low-battery lights cut holds the RGB dark through every stage. */
static void l_lights_cut(void) {
    power_init();
    on_battery_mid();
    power_set_lights_cut(true);
    CHECK(scale == 0, "cut while active: scale %u", scale);
    idle_ms = 600000; ltick();
    CHECK(scale == 0 && power_val_cap() == 64, "cut and dim: scale %u, cap %u", scale, power_val_cap());
    idle_ms = 0; ltick();
    CHECK(scale == 0, "cut after the wake: scale %u", scale);
    power_set_lights_cut(false);
    CHECK(scale == 255, "lifted: scale %u", scale);
    /* The cut around a ceiling move: Fn+B into Saver under the cut takes the
     * 128 at once (one repaint, still dark), and the lift shows it. */
    power_set_lights_cut(true);
    int r0 = rgb_restarts;
    power_cycle_mode(); ltick();   /* Saver, typing */
    expect_stage(POWER_STAGE_ACTIVE, 0, 0xFF, 128, "cut, Fn+B into Saver");
    expect_one_repaint(r0, "Saver's ceiling under the cut");
    r0 = rgb_restarts;
    power_set_lights_cut(false);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "the cut lifted in Saver");
    expect_one_repaint(r0, "the cut lifted in Saver");
}

/* A mode left unset (a flash) is Normal, and the overlay says so once, 3 s
 * after boot; a persisted one is taken silently. */
static void l_announce(void) {
    power_init();
    lrun_s(2);
    CHECK(last_status[0] == 0, "nothing before 3 s, got '%s'", last_status);
    lrun_s(2);
    CHECK(!strcmp(last_status, NAME_NORMAL), "overlay '%s'", last_status);
    uint8_t m = 0xFF;
    CHECK(kb_eeconfig_get_power_mode(&m) && m == POWER_MODE_NORMAL, "persisted %u", m);
}

/* Minimal: dark on battery even while typing; the backlight lights for 4 s
 * after a message and while Fn+D's pages are open; USB is Full. The model
 * pays for the lift: battery_power_uw() is the base, plus the backlight's
 * share at the user's level (10, duty 10/48) only while it is lit. */
#define MIN_DARK_UW 106900u
#define MIN_LIT_UW  (106900u + 39100u * 10u / 48u)
static void l_minimal(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_MINIMAL);
    power_init();
    on_battery_mid();
    idle_ms = 0; ltick();
    expect_stage(POWER_STAGE_SCREEN_OFF, 0, 0, 255, "Minimal, typing");
    CHECK(battery_power_uw() == MIN_DARK_UW, "dark: model %u uW, want %u", battery_power_uw(), MIN_DARK_UW);
    display_set_param_status("Brightness 5");   /* a key's overlay */
    uint32_t t0 = now_ms;
    ltick();
    CHECK(bkl_cap == 0xFF && scale == 0, "lit for the message, RGB still off: cap %u scale %u", bkl_cap, scale);
    CHECK(power_stage() == POWER_STAGE_SCREEN_OFF, "the stage stays the ladder's: %d", power_stage());
    lrun_s(2);
    CHECK(battery_power_uw() == MIN_LIT_UW, "lit: model %u uW, want %u", battery_power_uw(), MIN_LIT_UW);
    while (now_ms - t0 < 3900u) ltick();
    CHECK(bkl_cap == 0xFF, "still lit at 3.9 s: cap %u", bkl_cap);
    ltick();
    CHECK(now_ms - t0 == 4000u && bkl_cap == 0, "dark at 4.0 s: cap %u at %u ms", bkl_cap, now_ms - t0);
    lrun_s(2);
    CHECK(battery_power_uw() == MIN_DARK_UW, "dark again: model %u uW", battery_power_uw());
    display_set_alert("Battery low");           /* an alert lights it too */
    ltick();
    CHECK(bkl_cap == 0xFF, "lit for an alert: cap %u", bkl_cap);
    lrun_s(5);
    CHECK(bkl_cap == 0, "dark after the alert's 4 s: cap %u", bkl_cap);
    debug_open = true; ltick();
    CHECK(bkl_cap == 0xFF, "lit while Fn+D's page is open: cap %u", bkl_cap);
    lrun_s(30);
    CHECK(bkl_cap == 0xFF, "for as long as it is open: cap %u", bkl_cap);
    debug_open = false; ltick();
    CHECK(bkl_cap == 0, "dark when it closes: cap %u", bkl_cap);
    become_full(); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Minimal on USB");
}

/* Fn+B into Minimal while typing: dark at once but for its own overlay, which
 * it lights for 4 s like any other message. */
static void l_minimal_enter(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_SAVER);
    power_init();
    on_battery_mid();
    idle_ms = 0; ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver, typing");
    power_cycle_mode();
    CHECK(power_mode() == POWER_MODE_MINIMAL && !strcmp(last_status, NAME_MINIMAL),
          "mode %d, overlay '%s'", power_mode(), last_status);
    ltick();
    CHECK(power_stage() == POWER_STAGE_SCREEN_OFF && scale == 0 && bkl_cap == 0xFF,
          "RGB off, lit for 'Minimal mode': stage %d scale %u cap %u", power_stage(), scale, bkl_cap);
    lrun_s(4);
    CHECK(bkl_cap == 0, "dark after it: cap %u", bkl_cap);
}

/* A "Saving power" owed in Saver (low, the screen dark) is not given over
 * Fn+B's NAME_MINIMAL, nor anywhere in Minimal; it waits, and is given on
 * the way out, after the next mode's own overlay has had its 2 s. */
static void l_minimal_owed(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_SAVER);
    power_init();
    vdd_mv = 3900; c5 = 62;   /* ~11%: below the low cap */
    idle_ms = 300000;         /* Saver's screen-off: the notice is owed, unseen */
    lrun_s(30);
    CHECK(battery_level_permille() <= 150, "level %u pm, want <= 150", battery_level_permille());
    CHECK(last_status[0] == 0 && bkl_cap == 0, "owed, not shown: '%s', cap %u", last_status, bkl_cap);
    power_cycle_mode();       /* Fn+B: Saver -> Minimal */
    lrun_s(10);
    CHECK(!strcmp(last_status, NAME_MINIMAL), "Minimal's overlay kept, got '%s'", last_status);
    idle_ms = 0;              /* typing in Minimal: still dark, still not said */
    lrun_s(5);
    CHECK(!strcmp(last_status, NAME_MINIMAL), "nothing said in Minimal, got '%s'", last_status);
    power_cycle_mode();       /* Minimal -> Full: low, so Saver's ladder, lit while typing */
    uint32_t t0 = now_ms;
    lrun_s(1);
    CHECK(!strcmp(last_status, NAME_FULL), "'Full power' first, got '%s'", last_status);
    while (now_ms - t0 < 2500u) ltick();
    CHECK(!strcmp(last_status, "Saving power"), "then the owed notice, got '%s'", last_status);
}

/* Notices into a free band only: behind an alert (60 s from its post) the
 * flash's NAME_NORMAL and the low cap's "Saving power" would expire
 * unseen, so they wait it out, then come one after the other. */
static void l_low_alert(void) {
    power_init();
    display_set_alert("Watchdog reset");   /* as at a boot after a reset */
    uint32_t t0 = now_ms;
    vdd_mv = 3900; c5 = 62;                /* ~11%: under the low cap */
    while (now_ms - t0 < 59900u) ltick();
    CHECK(battery_level_permille() <= 150, "level %u pm, want <= 150", battery_level_permille());
    CHECK(last_status[0] == 0, "nothing over the alert, got '%s'", last_status);
    while (now_ms - t0 < 60500u) ltick();
    CHECK(!strcmp(last_status, NAME_NORMAL), "the announcement once it ends, got '%s'", last_status);
    while (now_ms - t0 < 63000u) ltick();
    CHECK(!strcmp(last_status, "Saving power"), "then the low notice, got '%s'", last_status);
}

static void l_persisted(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_SAVER);
    power_init();
    lrun_s(5);
    CHECK(power_mode() == POWER_MODE_SAVER, "mode %d", power_mode());
    CHECK(last_status[0] == 0, "no overlay for a persisted mode, got '%s'", last_status);
}

/* The deep sleep's times (plans/POWER-MODES-REVISION-PLAN.md): Normal at
 * 20 min, Saver at 3, Minimal after 1, Full never (low battery too); low
 * battery takes Normal to Saver's 3; never on USB. The screen is off by then
 * in every mode. */
static void l_sleep(void) {
    power_init();
    on_battery_mid();
    struct { power_mode_t m; uint32_t t; } want[] = {
        {POWER_MODE_NORMAL, 1200000u}, {POWER_MODE_SAVER, 180000u}, {POWER_MODE_MINIMAL, 60000u}};
    for (unsigned k = 0; k < 3; k++) {
        while (power_mode() != want[k].m) power_cycle_mode();
        idle_ms = want[k].t - 1u; ltick();
        CHECK(!power_sleep_wanted(), "mode %d: awake 1 ms before %u", want[k].m, want[k].t);
        idle_ms = want[k].t; ltick();
        CHECK(power_sleep_wanted(), "mode %d: asleep at %u ms", want[k].m, want[k].t);
        CHECK(power_stage() == POWER_STAGE_SCREEN_OFF, "mode %d: the screen off by then: stage %d", want[k].m,
              power_stage());
        idle_ms = 0; ltick();
        CHECK(!power_sleep_wanted(), "mode %d: a key ends it", want[k].m);
    }
    while (power_mode() != POWER_MODE_FULL) power_cycle_mode();
    idle_ms = 86400000u; ltick();
    CHECK(!power_sleep_wanted(), "Full never sleeps");
}

static void l_sleep_low(void) {
    power_init();
    vdd_mv = 3900; c5 = 62;   /* ~11%: the low cap */
    lrun_s(30);
    idle_ms = 179999; ltick();
    CHECK(!power_sleep_wanted(), "low, Normal: awake before 3 min");
    idle_ms = 180000; ltick();
    CHECK(power_sleep_wanted(), "low, Normal: asleep at Saver's 3 min");
    while (power_mode() != POWER_MODE_FULL) power_cycle_mode();
    idle_ms = 86400000u; ltick();
    CHECK(!power_sleep_wanted(), "low, Full: never");
    CHECK(power_stage() != POWER_STAGE_ACTIVE, "though Full's lighting still follows Saver's stages when low");
}

static void l_sleep_usb(void) {
    power_init();
    become_full();
    idle_ms = 86400000u;
    lrun_s(2);
    CHECK(!power_sleep_wanted(), "never on USB");
}

/* A wake after a long sleep says the time left in hours of use, once it
 * matters (under 10 h, the average mature), through the owed gate: a free
 * band, and a lit screen except in Minimal (codex, deep-sleep verify V7). */
static void l_wake_notice(void) {
    power_init();
    vdd_mv = 3900; c5 = 72;   /* ~3.79 V: ~200 pm, ~10 h at the sim's ~300.7 mW; above the low cap */
    lrun_s(30);
    idle_ms = 0;
    lrun_s(61 * 60);          /* a mature average */
    uint16_t left = battery_time_left_min();
    CHECK(left < 600u, "under 10 h left for the test: %u min", left);
    last_status[0] = 0;
    power_wake_notice();
    ltick();
    char want[16];
    snprintf(want, sizeof want, left < 60 ? "<1h use left" : "%uh use left", (unsigned)(left / 60u));
    CHECK(!strcmp(last_status, want), "the notice '%s', want '%s'", last_status, want);
    /* Behind a busy band it waits, and is given when the band frees. */
    display_set_param_status("Normal power");
    last_status[0] = 0;
    power_wake_notice();
    ltick();
    CHECK(last_status[0] == 0, "waits behind a busy band: '%s'", last_status);
    lrun_s(3);
    CHECK(!strncmp(last_status, want, strlen(want)), "then given: '%s'", last_status);
}

/* With hours to spare (the plateau, ~689 pm: ~35 h), nothing. */
static void l_wake_notice_high(void) {
    power_init();
    vdd_mv = 3900; c5 = 96;
    lrun_s(30);
    idle_ms = 0;
    lrun_s(61 * 60);
    CHECK(battery_time_left_min() >= 600u, "over 10 h left: %u min", battery_time_left_min());
    last_status[0] = 0;
    power_wake_notice();
    lrun_s(3);
    CHECK(last_status[0] == 0, "over 10 h: no notice ('%s')", last_status);
}

/* Above the low cap no mode reaches LIGHTS_OFF (l_low_cap sweeps below it). */
static void l_no_lights_off(void) {
    power_init();
    on_battery_mid();
    sweep_no_lights_off("mid level");
}

/* Power saver's ceiling moves with no stage change: each move repaints once,
 * and the next ticks nothing (plans/POWER-MODES-REVISION-PLAN.md, firmware
 * step 3). A boot with Saver persisted, Fn+B into Saver while typing, the
 * cable in and out while typing. */
static void l_ceiling_moves(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_SAVER);
    power_init();
    int r0 = rgb_restarts;
    on_battery_mid();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "a boot in Saver, on battery");
    expect_one_repaint(r0, "a boot in Saver");

    /* The cable in: Always on's lighting, at once. */
    r0 = rgb_restarts;
    vdd_mv = 4470; chrg_low = false; c5 = 100;
    lrun_s(30);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Saver, on USB");
    expect_one_repaint(r0, "Saver, the cable in");

    /* And out. */
    r0 = rgb_restarts;
    vdd_mv = 3900; c5 = 80;
    lrun_s(30);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver, back on battery");
    expect_one_repaint(r0, "Saver, the cable out");

    /* Fn+B: Saver -> Minimal -> Full -> Normal -> Saver, typing throughout. */
    power_cycle_mode(); lrun_s(5);   /* Minimal: dark, its overlay lit */
    power_cycle_mode(); lrun_s(1);   /* Full */
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Full, typing");
    r0 = rgb_restarts;
    power_cycle_mode(); lrun_s(1);   /* Normal: the same 255, nothing to repaint */
    CHECK(rgb_restarts == r0, "Full -> Normal while typing: %d repaints, want none", rgb_restarts - r0);
    r0 = rgb_restarts;
    power_cycle_mode(); ltick();     /* Saver */
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Fn+B into Saver, typing");
    expect_one_repaint(r0, "Fn+B into Saver");
}

/* The low cap's edge, at exactly 151 and 150 pm on the count's way down (5C
 * 68 boots at ~160 pm; 1 pm every ~186 s at the sim's load), and its exit on
 * the cable. In Normal, typing: 255 at 151, 128 at 150. */
static void l_low_edge(void) {
    power_init();
    vdd_mv = 3900; c5 = 68;
    lrun_s(30);
    idle_ms = 0;
    uint16_t lv = battery_level_permille();
    CHECK(lv > 151 && lv < 200, "the start, ~160 pm: %u", lv);
    for (uint32_t i = 0; i < 36000u && battery_level_permille() > 151; i++) ltick();
    CHECK(battery_level_permille() == 151, "the count passes 151: %u", battery_level_permille());
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "151 pm, Normal, typing");
    CHECK(power_lights_mode() == POWER_MODE_NORMAL, "151 pm: the bulb %d", power_lights_mode());
    int r0 = rgb_restarts;
    for (uint32_t i = 0; i < 36000u && battery_level_permille() > 150; i++) ltick();
    CHECK(battery_level_permille() == 150, "then 150: %u", battery_level_permille());
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "150 pm, Normal, typing");
    CHECK(power_lights_mode() == POWER_MODE_SAVER, "150 pm: the bulb %d", power_lights_mode());
    expect_one_repaint(r0, "the low cap's entry");
    idle_ms = 59999; ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "150 pm, Normal, 59.999 s");
    idle_ms = 60000; ltick(); expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "150 pm, Normal, 1 min");
    CHECK(!power_sleep_wanted(), "150 pm, Normal: awake at 1 min");
    idle_ms = 180000; ltick(); expect_stage(POWER_STAGE_SCREEN_OFF, 0, 0, 255, "150 pm, Normal, 3 min");
    CHECK(power_sleep_wanted(), "150 pm, Normal: asleep at Saver's 3 min");
    idle_ms = 0; ltick();
    r0 = rgb_restarts;
    vdd_mv = 4470; chrg_low = false; c5 = 100;   /* the cable: the cap lapses */
    lrun_s(30);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "the low cap's exit, on USB");
    expect_one_repaint(r0, "the low cap's exit");
}

/* An unknown level on battery (no 5C report yet) is not low: Normal's own
 * ceiling and stages, and Full's. */
static void l_unknown_level(void) {
    power_init();
    vdd_mv = 3900; c5 = 0xFF;   /* the module silent */
    lrun_s(30);
    CHECK(battery_level_permille() == 0xFFFFu, "unknown: %u", battery_level_permille());
    idle_ms = 0;      ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "unknown, Normal, typing");
    idle_ms = 180000; ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "unknown, Normal, 3 min");
    CHECK(!power_sleep_wanted(), "unknown, Normal: not asleep at Saver's 3 min");
    CHECK(power_lights_mode() == POWER_MODE_NORMAL, "unknown: the bulb %d", power_lights_mode());
    while (power_mode() != POWER_MODE_FULL) power_cycle_mode();
    idle_ms = 0;      ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "unknown, Full, typing");
    idle_ms = 600000; ltick(); expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "unknown, Full, 10 min");
}

#ifdef AK820_DEV_HOOKS
/* The bench's held stage takes the mode's ceiling whatever the supply, so
 * ladder_check.py can measure Saver's on USB against Full's. */
static void l_forced_ceiling(void) {
    power_init();
    become_full(); lrun_s(2);
    power_set_mode(POWER_MODE_SAVER); lrun_s(1);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Saver on USB, nothing held");
    int r0 = rgb_restarts;
    power_force_stage(POWER_STAGE_ACTIVE); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver on USB, ACTIVE held");
    expect_one_repaint(r0, "ACTIVE held in Saver on USB");
    r0 = rgb_restarts;
    power_set_mode(POWER_MODE_FULL); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Full on USB, ACTIVE held");
    expect_one_repaint(r0, "Saver -> Full, ACTIVE held");
    r0 = rgb_restarts;
    power_force_stage(0xFF); lrun_s(1);
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Full on USB, released");
    CHECK(rgb_restarts == r0, "released into the same lighting: %d repaints", rgb_restarts - r0);
    /* Released from Saver's held 128 on USB: back to no ceiling, once. */
    power_set_mode(POWER_MODE_SAVER); power_force_stage(POWER_STAGE_ACTIVE); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "Saver on USB, ACTIVE held again");
    r0 = rgb_restarts;
    power_force_stage(0xFF); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "Saver on USB, released");
    expect_one_repaint(r0, "Saver's held ACTIVE released on USB");
    power_force_stage(POWER_STAGE_LIGHTS_OFF); ltick();
    expect_stage(POWER_STAGE_LIGHTS_OFF, 0, SIM_DIM_CAP, 255, "LIGHTS_OFF held: still reachable by the bench");
    power_force_stage(0xFF); ltick();
}

/* Below 15%, the low cap's 128 holds in every mode, Lights out included
 * (plans/POWER-MODES-REVISION-PLAN.md, "Implementation": Lights out reaches
 * ACTIVE only held by the bench, so that is the one case it changes). */
static void l_low_minimal_held(void) {
    kb_eeconfig_set_power_mode(POWER_MODE_MINIMAL);
    power_init();
    vdd_mv = 3900; c5 = 62;   /* ~11%: under the low cap */
    lrun_s(30);
    CHECK(battery_level_permille() <= 150, "level %u pm, want <= 150", battery_level_permille());
    idle_ms = 0; ltick();
    CHECK(power_stage() == POWER_STAGE_SCREEN_OFF && scale == 0, "low, Lights out, typing: dark (stage %d, scale %u)",
          power_stage(), scale);
    power_force_stage(POWER_STAGE_ACTIVE); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "low, Lights out, ACTIVE held: the low cap's 128");
    CHECK(power_lights_mode() == POWER_MODE_MINIMAL, "low, Lights out: its own bulb, %d", power_lights_mode());
    power_force_stage(0xFF); ltick();
    CHECK(power_stage() == POWER_STAGE_SCREEN_OFF && scale == 0 && power_val_cap() == 255,
          "low, Lights out, released: stage %d, scale %u, cap %u", power_stage(), scale, power_val_cap());
}

/* The bench's mode change (op 14 sub 1), on battery while typing: Saver's
 * ceiling and back, once each. */
static void l_set_mode(void) {
    power_init();
    on_battery_mid();
    idle_ms = 0; ltick();
    int r0 = rgb_restarts;
    power_set_mode(POWER_MODE_SAVER); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "power_set_mode(Saver), typing");
    expect_one_repaint(r0, "power_set_mode into Saver");
    r0 = rgb_restarts;
    power_set_mode(POWER_MODE_NORMAL); ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 255, "power_set_mode(Normal), typing");
    expect_one_repaint(r0, "power_set_mode out of Saver");
}

/* Under the dim, a new ceiling for ACTIVE changes nothing applied: no
 * repaint, and no apply() after the one that takes it. */
static void l_under_dim(void) {
    power_init();
    on_battery_mid();
    power_force_stage(POWER_STAGE_DIM); ltick();
    expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "DIM held, Normal");
    int r0 = rgb_restarts;
    power_set_mode(POWER_MODE_SAVER); ltick();
    expect_stage(POWER_STAGE_DIM, 255, 0xFF, 64, "DIM held, Saver");
    power_set_mode(POWER_MODE_NORMAL); ltick();
    power_set_mode(POWER_MODE_SAVER); ltick();
    CHECK(rgb_restarts == r0, "Saver's ceiling under the dim: %d repaints, want none", rgb_restarts - r0);
    int s1 = scale_sets;
    lrun_s(2);
    CHECK(scale_sets == s1, "under the dim in Saver: %d applies on unchanged ticks", scale_sets - s1);
    power_force_stage(0xFF); idle_ms = 0; ltick();
    expect_stage(POWER_STAGE_ACTIVE, 255, 0xFF, 128, "released, Saver, typing");
}
#endif
