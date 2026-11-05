/* The colour path through QMK's real conversion: quantum/color.c and its CIE
 * table, linked in this build (SIM_REAL_COLOUR) in place of sim.c's stub, with
 * QMK's own colour types (stubs/quantum.h includes quantum/color.h here), and
 * the board's own effects (rgb_matrix_kb.inc) compiled here. #included by
 * sim.c; run.sh builds it as sim_colour.
 *
 * What it checks (plans/POWER-MODES-REVISION-PLAN.md, firmware step 4 and
 * "Host side"), for the dim's 64 and Power saver's 128, each set through
 * power.c's own ladder:
 * - k_hook: every colour at every user value converts as the same colour at
 *   min(value, ceiling), so a value at or under the ceiling is never changed
 *   and nothing drives above the ceiling's own drive;
 * - k_drift: DRIFT under a ceiling is DRIFT at min(value, ceiling) with no
 *   ceiling, frame for frame (option c: the palette built uncapped, the value
 *   knob capped): every value from an init, and one stream with the palette's
 *   cache warm while hue, saturation, value and the ceiling change;
 * - k_drift_usb: DRIFT with no ceiling (USB) renders exactly as before the
 *   revision. A stream across speeds and warm-cache changes, hashed against
 *   DRIFT_USB_FNV, which run.sh re-derives from 8b06e4dcc4's own DRIFT;
 * - k_rainfall: RAINFALL, which converts each drop's own value, never drives
 *   above the ceiling's drive (at nine values, not every one).
 *
 * The frames run as rgb_matrix.c runs them: the board's 81 LEDs in QMK's
 * default 5 chunks, init on every chunk of a first frame. The LED positions
 * are a synthetic grid across the board's 217 x 59, not its map: enough to
 * reach every cell of DRIFT's ramp, not a claim about the board's frames.
 *
 * On the wide path (D9, SIM_WIDE_EFFECTS, a power.c with power_local_value_mode)
 * an effect renders chroma and the flush applies the value and the cap, so a
 * render buffer says nothing about light. There these checks read final widths,
 * in quarter ticks, through a copy of rowisr.c's flush arithmetic and the real
 * power_val_cap(): k_hook checks a uniform effect's chroma and final width, a
 * local-value effect's uncapped conversion, and a mode off the list keeping the
 * old hook; k_drift compares final widths; k_drift_usb hashes DRIFT's bytes,
 * which no longer depend on the value; k_rainfall bounds the final widths and
 * requires a drop's full chroma; k_restart checks a wide mode's cap change
 * restarts nothing while a scale change does. */

/* What rgb_matrix_kb.inc takes from QMK's rgb_matrix, for its two effects on
 * a host. lib8tion's formulas as the board builds them (SCALE8_C, and
 * FASTLED_SCALE8_FIXED=1 from builddefs/common_features.mk's LIB8TION_ENABLE;
 * lib8tion's own headers carry AVR asm a host compiler refuses). */
typedef uint8_t fract8;
static inline uint8_t scale8(uint8_t i, fract8 s) { return (uint8_t)(((uint16_t)i * (1u + (uint16_t)s)) >> 8); }
static inline uint8_t qsub8(uint8_t i, uint8_t j) { int16_t t = (int16_t)(i - j); return (uint8_t)(t < 0 ? 0 : t); }
static uint16_t rand16seed = 1337;
static inline uint8_t random8(void) {
    rand16seed = (uint16_t)(rand16seed * 2053u + 13849u);
    return (uint8_t)((uint8_t)(rand16seed & 0xFF) + (uint8_t)(rand16seed >> 8));
}
static inline uint8_t random8_max(uint8_t lim) { return (uint8_t)((random8() * lim) >> 8); }
typedef struct { uint8_t iter; bool init; } effect_params_t;
static struct { hsv_t hsv; uint8_t speed; } rgb_matrix_config;

#undef RGB_MATRIX_LED_COUNT
#define RGB_MATRIX_LED_COUNT 81                          /* the board's (keyboard.json) */
#define K_LIMIT ((RGB_MATRIX_LED_COUNT + 4) / 5)          /* QMK's default RGB_MATRIX_LED_PROCESS_LIMIT */
static struct { struct { uint8_t x, y; } point[RGB_MATRIX_LED_COUNT]; } g_led_config;
static rgb_t k_frame[RGB_MATRIX_LED_COUNT];
static void rgb_matrix_set_color(int i, uint8_t r, uint8_t g, uint8_t b) { k_frame[i] = (rgb_t){r, g, b}; }
static bool rgb_matrix_check_finished_leds(uint8_t led_max) { return led_max < RGB_MATRIX_LED_COUNT; }
#define RGB_MATRIX_EFFECT(name)
#define RGB_MATRIX_CUSTOM_EFFECT_IMPLS
#define RGB_MATRIX_USE_LIMITS(min, max)                \
    uint8_t min = (uint8_t)(K_LIMIT * params->iter), \
            max = (uint8_t)((min) + K_LIMIT < RGB_MATRIX_LED_COUNT ? (min) + K_LIMIT : RGB_MATRIX_LED_COUNT)
#define RGB_MATRIX_TEST_LED_FLAGS()
#include "rgb_matrix_kb.inc"

/* What a test compares: the light that reaches the LEDs. */
#ifdef SIM_WIDE_EFFECTS
#include "curve12.h"
#include "flush_dirty.h"
typedef struct { uint16_t r, g, b; } k_out_t;
static uint32_t k_recips[256];
static uint32_t k_recip(uint8_t v) {
    if (!k_recips[255])
        for (unsigned i = 0; i < 256; i++) {   /* rowisr.c's flush at the 125 us cadence's K */
            uint32_t full_q8 = ((uint32_t)curve_q6[i] * 300u) >> 4;
            k_recips[i] = (full_q8 * 256u + 127u) / 255u;
        }
    return k_recips[v];
}
static uint16_t k_quarters(uint8_t chroma, uint32_t recip) {   /* wide_width()'s mean, in quarter ticks */
    uint32_t q8 = ((uint32_t)chroma * recip + 128u) >> 8, w = q8 >> 8, frac = q8 & 0xFFu;
    if (w >= 16u) return (uint16_t)((w + (frac >= 128u ? 1u : 0u)) * 4u);
    return (uint16_t)(w * 4u + ((frac + 32u) >> 6));
}
static k_out_t k_out(rgb_t c, uint8_t v) {   /* the flush: the config's value under the ladder's cap */
    uint32_t r = k_recip(v < power_val_cap() ? v : power_val_cap());
    return (k_out_t){k_quarters(c.r, r), k_quarters(c.g, r), k_quarters(c.b, r)};
}
#else
typedef rgb_t k_out_t;
static k_out_t k_out(rgb_t c, uint8_t v) { (void)v; return c; }
#endif
static bool k_out_same(k_out_t a, k_out_t b) { return a.r == b.r && a.g == b.g && a.b == b.b; }
static bool k_out_lit(k_out_t a) { return a.r || a.g || a.b; }

/* One frame as rgb_matrix.c renders it: chunk after chunk until the effect
 * says the board is done, `init` on every chunk of a first frame. */
static void k_run(bool (*fx)(effect_params_t *), bool init) {
    effect_params_t p = {.iter = 0, .init = init};
    while (fx(&p)) p.iter++;
}

static void k_points(void) {
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        g_led_config.point[i].x = (uint8_t)((i % 14u) * 16u + (i / 14u) * 3u);
        g_led_config.point[i].y = (uint8_t)((i / 14u) * 11u);
    }
}

/* The ceilings, through power.c: the dim (Normal at 10 min), Saver while
 * typing, and none (USB). Booted once; the mode is persisted, so each sets
 * its own. */
static bool k_booted;
static void k_on_battery(void) {
    if (!k_booted) { power_init(); k_booted = true; }
    on_battery_mid();
}
static void k_ceiling_dim(void) {
    k_on_battery();
    while (power_mode() != POWER_MODE_NORMAL) power_cycle_mode();
    idle_ms = 600000; ltick();
    CHECK(power_val_cap() == SIM_DIM_VAL, "the dim's ceiling: %u", power_val_cap());
}
static void k_ceiling_saver(void) {
    k_on_battery();
    while (power_mode() != POWER_MODE_SAVER) power_cycle_mode();
    idle_ms = 0; ltick();
    CHECK(power_val_cap() == SIM_SAVER_VAL, "Saver's ceiling: %u", power_val_cap());
}
static void k_ceiling_none(void) {
    vdd_mv = 4470; chrg_low = false; c5 = 100;
    lrun_s(30);
    CHECK(power_val_cap() == 255, "on USB, no ceiling: %u", power_val_cap());
}
static void k_ceiling(uint8_t cap) {
    if (cap == SIM_DIM_VAL) k_ceiling_dim();
    else if (cap == SIM_SAVER_VAL) k_ceiling_saver();
    else k_ceiling_none();
}

static uint8_t k_max3(rgb_t c) { return c.r > c.g ? (c.r > c.b ? c.r : c.b) : (c.g > c.b ? c.g : c.b); }
static bool    k_same(rgb_t a, rgb_t b) { return a.r == b.r && a.g == b.g && a.b == b.b; }

#ifdef SIM_WIDE_EFFECTS
/* Every hue, saturation and value of a uniform effect: the hook hands the flush
 * the chroma, and the final width is that chroma's at min(value, ceiling), never
 * above white's at the ceiling. A local-value effect keeps its own value through
 * the ceiling, and a mode off the list keeps the old hook (a stride of colours
 * for those two). */
static unsigned k_hook_at(uint8_t cap) {
    uint32_t rc = k_recip(cap);
    uint16_t top = k_quarters(255, rc);
    unsigned bad = 0;
    for (unsigned h = 0; h < 256; h++)
        for (unsigned s = 0; s < 256; s++) {
            rgb_t chroma = hsv_to_rgb((hsv_t){(uint8_t)h, (uint8_t)s, 255});
            rgb_mode = RGB_MATRIX_SOLID_COLOR;
            for (unsigned v = 0; v < 256; v++) {
                rgb_t got = rgb_matrix_hsv_to_rgb((hsv_t){(uint8_t)h, (uint8_t)s, (uint8_t)v});
                k_out_t o = k_out(got, (uint8_t)v);
                if (!k_same(got, chroma) || o.r > top || o.g > top || o.b > top) {
                    if (bad++ < 3)
                        CHECK(false, "cap %u: uniform hsv %u,%u,%u gives %u,%u,%u, want the chroma %u,%u,%u, top %u", cap, h, s, v,
                              got.r, got.g, got.b, chroma.r, chroma.g, chroma.b, top);
                }
            }
            if (h % 5u == 0 && s % 5u == 0)
                for (unsigned v = 0; v < 256; v++) {
                    hsv_t c = {(uint8_t)h, (uint8_t)s, (uint8_t)v};
                    rgb_mode = RGB_MATRIX_CUSTOM_RAINFALL;
                    rgb_t loc = rgb_matrix_hsv_to_rgb(c);
                    rgb_mode = 200;   /* off the list */
                    rgb_t off = rgb_matrix_hsv_to_rgb(c);
                    hsv_t w = c;
                    if (w.v > cap) w.v = cap;
                    if (!k_same(loc, hsv_to_rgb(c)) || !k_same(off, hsv_to_rgb(w))) {
                        if (bad++ < 3) CHECK(false, "cap %u: hsv %u,%u,%u: a local value or the old hook is wrong", cap, h, s, v);
                    }
                }
        }
    rgb_mode = 2;
    return bad;
}
#else
/* Every hue, saturation and value through the hook, against QMK's own
 * conversion at min(value, ceiling). */
static unsigned k_hook_at(uint8_t cap) {
    uint8_t  top = hsv_to_rgb((hsv_t){0, 0, cap}).r;   /* white at the ceiling: its CIE drive */
    unsigned bad = 0;
    for (unsigned h = 0; h < 256; h++)
        for (unsigned s = 0; s < 256; s++)
            for (unsigned v = 0; v < 256; v++) {
                hsv_t c = {(uint8_t)h, (uint8_t)s, (uint8_t)v};
                rgb_t got = rgb_matrix_hsv_to_rgb(c);
                hsv_t w = c;
                if (w.v > cap) w.v = cap;
                rgb_t want = hsv_to_rgb(w);
                if (!k_same(got, want) || k_max3(got) > top) {
                    if (bad++ < 3)
                        CHECK(false, "cap %u: hsv %u,%u,%u gives %u,%u,%u, want %u,%u,%u (top %u)", cap, h, s, v,
                              got.r, got.g, got.b, want.r, want.g, want.b, top);
                }
            }
    return bad;
}
#endif

static void k_hook(void) {
    k_ceiling_dim();
    CHECK(k_hook_at(SIM_DIM_VAL) == 0, "the dim's ceiling, every colour");
    k_ceiling_saver();
    CHECK(k_hook_at(SIM_SAVER_VAL) == 0, "Saver's ceiling, every colour");
    CHECK(hsv_to_rgb((hsv_t){0, 0, 128}).r == 48 && hsv_to_rgb((hsv_t){0, 0, 64}).r == 12,
          "QMK's CIE table: 128 drives 48, 64 drives 12");
    k_ceiling_none();
    CHECK(k_hook_at(255) == 0, "no ceiling: the hook is QMK's conversion");
}

/* DRIFT's frames at one value: the init frame and K_FRAMES - 1 after it, at a
 * mid speed so the field moves between them. */
#define K_FRAMES 6
static void k_drift_frames(hsv_t c, k_out_t out[K_FRAMES][RGB_MATRIX_LED_COUNT]) {
    rgb_matrix_config.hsv   = c;
    rgb_matrix_config.speed = 200;
    for (unsigned f = 0; f < K_FRAMES; f++) {
        k_run(DRIFT, f == 0);
        for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) out[f][i] = k_out(k_frame[i], c.v);
    }
}

static k_out_t k_capped[256][K_FRAMES][RGB_MATRIX_LED_COUNT];
static k_out_t k_free[256][K_FRAMES][RGB_MATRIX_LED_COUNT];

/* One stream from a single init, the palette's cache warm throughout: each
 * step K_STEP_FRAMES frames at its hue, saturation and value, under its
 * ceiling. */
typedef struct { uint8_t h, s, v, cap; } k_step_t;
static const k_step_t k_stream[] = {
#define KS SIM_SAVER_VAL
#define KD SIM_DIM_VAL
    {191, 255, 200, KS}, {191, 255, 200, KD}, {191, 255, 200, KS},   /* the ceiling moves */
    {30, 255, 200, KS},  {30, 120, 200, KS},                         /* hue, then saturation */
    {30, 120, 90, KS},   {30, 120, 90, KD},   {30, 120, 255, KD},    /* under and over each */
    {0, 0, 255, KS},     {0, 0, 200, KD},     {213, 64, 160, KS},
};
#define K_STEPS       (sizeof k_stream / sizeof k_stream[0])
#define K_STEP_FRAMES 4
static k_out_t k_stream_a[K_STEPS][K_STEP_FRAMES][RGB_MATRIX_LED_COUNT];
static k_out_t k_stream_b[K_STEPS][K_STEP_FRAMES][RGB_MATRIX_LED_COUNT];

/* The stream under its ceilings (capped), or with none and the value at
 * min(value, ceiling) (free). The ceilings move between frames, as the
 * ladder moves them; DRIFT is never re-initialized. */
static void k_stream_run(bool capped, k_out_t out[K_STEPS][K_STEP_FRAMES][RGB_MATRIX_LED_COUNT]) {
    if (!capped) k_ceiling_none();
    rgb_matrix_config.speed = 200;
    for (unsigned k = 0; k < K_STEPS; k++) {
        k_step_t st = k_stream[k];
        if (capped) k_ceiling(st.cap);
        rgb_matrix_config.hsv = (hsv_t){st.h, st.s, capped ? st.v : (st.v < st.cap ? st.v : st.cap)};
        for (unsigned f = 0; f < K_STEP_FRAMES; f++) {
            k_run(DRIFT, k == 0 && f == 0);
            for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) out[k][f][i] = k_out(k_frame[i], rgb_matrix_config.hsv.v);
        }
    }
}

static void k_drift(void) {
    static const uint8_t hs[][2] = {{0, 255}, {170, 255}, {85, 128}, {213, 64}, {40, 0}};
    k_points();
#ifdef SIM_WIDE_EFFECTS
    rgb_mode = RGB_MATRIX_CUSTOM_DRIFT;
#endif
    for (unsigned pass = 0; pass < 2; pass++) {
        uint8_t cap = pass == 0 ? SIM_DIM_VAL : SIM_SAVER_VAL;
        for (unsigned k = 0; k < sizeof hs / sizeof hs[0]; k++) {
            /* Each ceiling's frames for every value, then the same with no
             * ceiling (USB). */
            k_ceiling(cap);
            for (unsigned v = 0; v < 256; v++) k_drift_frames((hsv_t){hs[k][0], hs[k][1], (uint8_t)v}, k_capped[v]);
            k_ceiling_none();
            for (unsigned v = 0; v < 256; v++) k_drift_frames((hsv_t){hs[k][0], hs[k][1], (uint8_t)v}, k_free[v]);
            unsigned bad = 0, lit = 0;
            for (unsigned v = 0; v < 256; v++) {
                unsigned ve = v < cap ? v : cap;
                for (unsigned f = 0; f < K_FRAMES; f++)
                    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
                        k_out_t a = k_capped[v][f][i], b = k_free[ve][f][i];
                        if (k_out_lit(a)) lit++;
                        if (!k_out_same(a, b) && bad++ < 3)
                            CHECK(false, "cap %u, hue %u sat %u, value %u, frame %u, LED %u: %u,%u,%u, want %u,%u,%u",
                                  cap, hs[k][0], hs[k][1], v, f, i, a.r, a.g, a.b, b.r, b.g, b.b);
                    }
            }
            CHECK(bad == 0, "cap %u, hue %u sat %u: %u LED frames differ", cap, hs[k][0], hs[k][1], bad);
            CHECK(lit > 0, "cap %u, hue %u sat %u: nothing lit, so nothing compared", cap, hs[k][0], hs[k][1]);
        }
        printf("  DRIFT under %u matches DRIFT at min(value, %u), %u values x %u frames x %u LEDs x %u colours\n",
               cap, cap, 256u, K_FRAMES, RGB_MATRIX_LED_COUNT, (unsigned)(sizeof hs / sizeof hs[0]));
    }
    k_stream_run(true, k_stream_a);
    k_stream_run(false, k_stream_b);
    unsigned bad = 0, lit = 0;
    for (unsigned k = 0; k < K_STEPS; k++)
        for (unsigned f = 0; f < K_STEP_FRAMES; f++)
            for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
                k_out_t a = k_stream_a[k][f][i], b = k_stream_b[k][f][i];
                if (k_out_lit(a)) lit++;
                if (!k_out_same(a, b) && bad++ < 3)
                    CHECK(false, "the warm stream, step %u frame %u LED %u: %u,%u,%u, want %u,%u,%u", k, f, i, a.r,
                          a.g, a.b, b.r, b.g, b.b);
            }
    CHECK(bad == 0 && lit > 0, "the warm stream: %u LED frames differ, %u lit", bad, lit);
    printf("  and with the cache warm: %u steps x %u frames, the ceiling, hue, saturation and value moving\n",
           (unsigned)K_STEPS, K_STEP_FRAMES);
}

/* DRIFT on USB, hashed: three speeds, each one stream from an init with the
 * cache warm across hue, saturation and value changes. DRIFT_USB_FNV is the
 * hash 8b06e4dcc4's DRIFT gives (run.sh builds that DRIFT and checks it), so
 * the revision leaves USB rendering exactly as it was. */
#ifdef SIM_WIDE_EFFECTS
/* DRIFT's bytes no longer depend on the value, and they are the old DRIFT's at
 * full value: run.sh builds 8b06e4dcc4's with SIM_DRIFT_USB_FULL and checks it. */
#define DRIFT_USB_FNV 0xd05750efu
#else
#define DRIFT_USB_FNV 0x41da838au
#endif
static void k_drift_usb(void) {
    static const uint8_t speeds[] = {0, 128, 255};
    static const hsv_t   steps[]  = {{191, 255, 255}, {191, 255, 120}, {30, 255, 120}, {30, 90, 120},
                                     {30, 90, 255},   {0, 0, 200},     {213, 64, 40},  {170, 255, 0}};
    k_points();
    k_ceiling_none();
#if defined(SIM_WIDE_EFFECTS) && !defined(SIM_DRIFT_USB_FULL)
    rgb_mode = RGB_MATRIX_CUSTOM_DRIFT;   /* not for the old DRIFT, whose palette goes through the wrap */
#endif
    uint32_t h = 2166136261u;
    unsigned lit = 0;
    for (unsigned sp = 0; sp < sizeof speeds; sp++) {
        rgb_matrix_config.speed = speeds[sp];
        for (unsigned k = 0; k < sizeof steps / sizeof steps[0]; k++) {
            rgb_matrix_config.hsv = steps[k];
#ifdef SIM_DRIFT_USB_FULL
            rgb_matrix_config.hsv.v = 255;
#endif
            for (unsigned f = 0; f < 6; f++) {
                k_run(DRIFT, k == 0 && f == 0);
                for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
                    const uint8_t b[3] = {k_frame[i].r, k_frame[i].g, k_frame[i].b};
                    if (k_max3(k_frame[i])) lit++;
                    for (unsigned j = 0; j < 3; j++) h = (h ^ b[j]) * 16777619u;
                }
            }
        }
    }
    printf("  DRIFT on USB: FNV-1a %08x over %u lit LED frames\n", (unsigned)h, lit);
    CHECK(h == DRIFT_USB_FNV, "DRIFT on USB renders differently: %08x, want %08x", (unsigned)h, DRIFT_USB_FNV);
    CHECK(lit > 0, "DRIFT on USB: nothing lit");
}

/* RAINFALL's drops, a few hundred frames at each value, never above the
 * ceiling's drive. */
static void k_rainfall_at(uint8_t cap) {
    static const uint8_t vs[] = {255, 200, 150, 129, 128, 100, 65, 64, 30};
#ifdef SIM_WIDE_EFFECTS
    rgb_mode = RGB_MATRIX_CUSTOM_RAINFALL;
    uint16_t top = k_quarters(255, k_recip(cap));
#else
    uint8_t  top = hsv_to_rgb((hsv_t){0, 0, cap}).r;
#endif
    unsigned bad = 0, lit = 0;
    for (unsigned k = 0; k < sizeof vs; k++) {
        rgb_matrix_config.hsv   = (hsv_t){0, 255, vs[k]};
        rgb_matrix_config.speed = 255;   /* a drop every frame */
#ifdef SIM_WIDE_EFFECTS
        uint8_t peak = 0;
#endif
        for (unsigned f = 0; f < 300; f++) {
            k_run(RAINFALL, f == 0);
            for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
#ifdef SIM_WIDE_EFFECTS
                k_out_t  o = k_out(k_frame[i], vs[k]);
                uint16_t m = o.r > o.g ? (o.r > o.b ? o.r : o.b) : (o.g > o.b ? o.g : o.b);
                if (k_max3(k_frame[i]) > peak) peak = k_max3(k_frame[i]);
#else
                uint8_t m = k_max3(k_frame[i]);
#endif
                if (m) lit++;
                if (m > top && bad++ < 3) CHECK(false, "cap %u, value %u: LED %u drives %u, top %u", cap, vs[k], i, m, top);
            }
        }
#ifdef SIM_WIDE_EFFECTS
        /* The top drops near full chroma at every value: the value and the cap are the flush's. */
        CHECK(peak >= 240, "RAINFALL under %u, value %u: the brightest fresh drop's chroma reaches %u", cap, vs[k], peak);
#endif
    }
    CHECK(bad == 0 && lit > 0, "RAINFALL under %u: %u over the ceiling, %u lit", cap, bad, lit);
#ifdef SIM_WIDE_EFFECTS
    rgb_mode = 2;
#endif
}

static void k_rainfall(void) {
    k_ceiling_dim();
    k_rainfall_at(SIM_DIM_VAL);
    k_ceiling_saver();
    k_rainfall_at(SIM_SAVER_VAL);
}

#ifdef SIM_WIDE_EFFECTS
/* A wide mode's cap change is the flush's alone: Rainfall, the Heatmap and Drift
 * keep their state across a dim. A scale change still restarts the effect, since
 * the scale applies as an LED is set, and a mode off the list restarts on either. */
static void k_restart(void) {
    k_ceiling_saver();
    rgb_mode = RGB_MATRIX_CUSTOM_RAINFALL;
    idle_ms = 0; ltick();
    int r = rgb_restarts;
    idle_ms = 60000; ltick();
    CHECK(power_val_cap() == SIM_DIM_VAL, "Saver's dim at 1 min: %u", power_val_cap());
    CHECK(rgb_restarts == r, "a wide mode restarted at the dim: %d", rgb_restarts - r);
    idle_ms = 0; ltick();
    CHECK(power_val_cap() == SIM_SAVER_VAL, "the key after the dim: %u", power_val_cap());
    CHECK(rgb_restarts == r, "a wide mode restarted at the dim's end: %d", rgb_restarts - r);
    idle_ms = 180000; ltick();
    CHECK(rgb_restarts > r, "the lights' scale changed and nothing restarted");
    idle_ms = 0; ltick();
    rgb_mode = 200;   /* off the list */
    r = rgb_restarts;
    idle_ms = 60000; ltick();
    CHECK(rgb_restarts == r + 1, "a mode off the list did not restart at the dim: %d", rgb_restarts - r);
    idle_ms = 0; ltick();
    rgb_mode = 2;
}

/* The flush's rule, from rowisr.c's own header: since a wide mode's cap change no longer
 * restarts the effect, a value change with no byte moved is the only way the cap reaches
 * the LEDs. Walked through the real ladder: each ceiling it moves to must call for a
 * conversion, once. */
static void k_flush(void) {
    CHECK(!rowisr_flush_dirty(false, true, true, 64, 64), "nothing changed");
    CHECK(rowisr_flush_dirty(true, true, true, 64, 64), "the bytes changed");
    CHECK(rowisr_flush_dirty(false, true, false, 64, 64), "into the wide path");
    CHECK(rowisr_flush_dirty(false, false, true, 64, 64), "out of it");
    CHECK(!rowisr_flush_dirty(false, false, false, 64, 128), "raw bytes take no value");
    k_ceiling_saver();
    rgb_mode = RGB_MATRIX_SOLID_COLOR;
    idle_ms = 0; ltick();
    uint8_t cfg = 255, last = cfg < power_val_cap() ? cfg : power_val_cap();
    CHECK(last == SIM_SAVER_VAL, "typing, at Saver's ceiling: %u", last);
    for (unsigned k = 0; k < 3; k++) {
        idle_ms = 60000; ltick();
        uint8_t v = cfg < power_val_cap() ? cfg : power_val_cap();
        CHECK(v == SIM_DIM_VAL && rowisr_flush_dirty(false, true, true, v, last), "into the dim: %u from %u", v, last);
        CHECK(!rowisr_flush_dirty(false, true, true, v, v), "the dim's next frame");
        last = v;
        idle_ms = 0; ltick();
        v = cfg < power_val_cap() ? cfg : power_val_cap();
        CHECK(v == SIM_SAVER_VAL && rowisr_flush_dirty(false, true, true, v, last), "out of the dim: %u from %u", v, last);
        last = v;
    }
    rgb_mode = 2;
}

#ifndef SIM_DRIFT_USB_FULL   /* the old DRIFT's tree has no RAIN */
/* RAIN: every LED the user's hue and saturation at the drop's own brightness, the
 * ceiling left to the flush, and the drops' tops spread from RAIN_PEAK_MIN to full. */
static void k_rain_at(uint8_t cap) {
    static const uint8_t cs[][2] = {{178, 219}, {0, 255}, {85, 128}, {40, 0}};
    uint16_t top = k_quarters(255, k_recip(cap));
    rgb_mode = RGB_MATRIX_CUSTOM_RAIN;
    unsigned bad = 0, lit = 0, seeds = 0, fell = 0, falls = 0;
    uint8_t  low = 255, high = 0;
    for (unsigned k = 0; k < sizeof cs / sizeof cs[0]; k++) {
        rgb_matrix_config.hsv   = (hsv_t){cs[k][0], cs[k][1], 200};
        rgb_matrix_config.speed = 255;   /* a drop every frame */
        for (unsigned f = 0; f < 600; f++) {
            uint8_t before[RGB_MATRIX_LED_COUNT];
            memcpy(before, rainfall_v, sizeof before);
            k_run(RAIN, f == 0);
            for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
                uint8_t v = rainfall_v[i];
                if (f && v > before[i]) {   /* a fresh drop */
                    seeds++;
                    if (v < low) low = v;
                    if (v > high) high = v;
                } else if (f && before[i] > 8 && before[i] - v <= 4) {   /* a falling drop, clear of the floor and not reseeded lower */
                    fell += (unsigned)(before[i] - v);
                    falls++;
                }
                rgb_t   want = hsv_to_rgb((hsv_t){cs[k][0], cs[k][1], v});
                k_out_t o    = k_out(k_frame[i], rgb_matrix_config.hsv.v);
                if (k_max3(k_frame[i])) lit++;
                if ((!k_same(k_frame[i], want) || o.r > top || o.g > top || o.b > top) && bad++ < 3)
                    CHECK(false, "cap %u, hsv %u,%u, frame %u, LED %u: %u,%u,%u at drop %u, want %u,%u,%u", cap, cs[k][0], cs[k][1], f,
                          i, k_frame[i].r, k_frame[i].g, k_frame[i].b, v, want.r, want.g, want.b);
            }
        }
    }
    CHECK(bad == 0 && lit > 0, "RAIN under %u: %u wrong, %u lit", cap, bad, lit);
    CHECK(seeds > 1000 && low >= RAIN_PEAK_MIN && low < RAIN_PEAK_MIN + 16 && high > 240,
          "RAIN under %u: %u drops, tops %u to %u", cap, seeds, low, high);
    /* The fade: 2.25 a frame, written out so a changed constant must change this too. */
    CHECK(falls > 1000 && fell * 16u > falls * 35u && fell * 16u < falls * 37u, "RAIN under %u: fell %u over %u frames of a drop", cap, fell, falls);
    printf("  RAIN under %u: %u drops, tops %u to %u, falling %.2f a frame\n", cap, seeds, low, high, (double)fell / falls);
    rgb_mode = 2;
}

static void k_rain(void) {
    k_ceiling_dim();
    k_rain_at(SIM_DIM_VAL);
    k_ceiling_saver();
    k_rain_at(SIM_SAVER_VAL);
}
#endif
#endif
