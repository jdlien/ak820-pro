/* Host test of the configuration menu's S0 foundations: the owner, session and
 * restore (menu/panel_owner.c), the knob's capture and op 27's single flight
 * (menu/menu_input.c), the damage model (menu/menu_slots.c) and the fixture
 * (menu/menu_fixture.c), against a fake framebuffer. These are the firmware's
 * own files: plans/CONFIG-MENU-BUILD-PLAN.md, "S0". Build and run:
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -I $D/menu scripts/menu_s0_test.c \
 *       $D/menu/panel_owner.c $D/menu/menu_input.c $D/menu/menu_slots.c \
 *       $D/menu/menu_fixture.c -o ms0 && ./ms0
 *
 * (On Windows, mingw64's gcc first on PATH: CLAUDE.md.) */
#include <stdio.h>
#include <string.h>

#include "menu_backend.h"
#include "menu_fixture.h"
#include "menu_input.h"
#include "menu_slots.h"
#include "panel_owner.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* --- the fake panel ----------------------------------------------------------
 * A glyph is a DMA: it arms (busy) and lands at the next pass's start, or is
 * lost if a fault was injected. A glyph's cell is painted as one colour, the
 * character's code, which is all the frames need to tell glyphs apart. */
static uint16_t fb[MB_H][MB_W];
static bool     dma_busy;
static uint16_t dma_x, dma_y, dma_col;
static bool     lost_latched;
static int      fault_next_dma;     /* the next N transfers are given up */
static int      fault_next_band;    /* the next N clear bands fail */
static bool     bus_busy_once;      /* the next glyph finds the bus busy */
static int      glyph_ops, fill_ops, bands_ok;

static void fill_fb(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t c) {
    for (uint16_t y = y0; y <= y1 && y < MB_H; y++)
        for (uint16_t x = x0; x <= x1 && x < MB_W; x++) fb[y][x] = c;
}
static uint16_t glyph_color(char c) { return (uint16_t)(0x8000u | (uint8_t)c); }

/* The pass boundary: an armed DMA completes, or is given up. */
static void dma_settle(void) {
    if (!dma_busy) return;
    dma_busy = false;
    if (fault_next_dma > 0) {
        fault_next_dma--;
        lost_latched = true;
        return;
    }
    fill_fb(dma_x, dma_y, (uint16_t)(dma_x + MB_GLYPH_W - 1), (uint16_t)(dma_y + MB_GLYPH_H - 1), dma_col);
}

bool mb_clear_band(uint8_t band) {
    dma_settle();   /* lcd_clear_rect quiesces first */
    if (fault_next_band > 0) {
        fault_next_band--;
        lost_latched = true;
        return false;
    }
    fill_fb(0, (uint16_t)(band * MB_BAND_H), MB_W - 1, (uint16_t)(band * MB_BAND_H + MB_BAND_H - 1), 0);
    bands_ok++;
    return true;
}
void mb_fill(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t c) {
    dma_settle();   /* bus_quiesce */
    fill_fb(x0, y0, x1, y1, c);
    fill_ops++;
}
bool mb_glyph(char c, uint16_t x, uint16_t y) {
    if (bus_busy_once) { bus_busy_once = false; return false; }
    if (dma_busy) return false;
    dma_busy = true;
    dma_x = x; dma_y = y; dma_col = glyph_color(c);
    glyph_ops++;
    return true;
}
bool mb_busy(void) { return dma_busy; }
bool mb_lost_pending(void) { return lost_latched; }
static bool take_lost(void) { bool l = lost_latched; lost_latched = false; return l; }

static void fake_reset(void) {
    memset(fb, 0x55, sizeof fb);   /* not black: a pixel the clear missed shows */
    dma_busy = lost_latched = bus_busy_once = false;
    fault_next_dma = fault_next_band = 0;
    glyph_ops = fill_ops = bands_ok = 0;
}

/* One pass of the menu's painter, as the pump runs it: the DMA's completion
 * first, the loss taken at the top, then one bounded operation. */
static ms_step_t pass(void) {
    dma_settle();
    if (take_lost()) fx_invalidate();
    return ms_step();
}
static int run_until_settled(int max) {
    for (int i = 0; i < max; i++) {
        pass();
        if (ms_settled() && !mb_busy()) return i + 1;
    }
    return -1;
}

/* The expected F1 frame, from the fixture's own tables. */
static uint16_t expect_f1(uint16_t x, uint16_t y, uint8_t pat, uint8_t row) {
    if (y < 14) {   /* the title row: glyph cells from x 4, the rest left by the clear */
        if (x >= 4 && x < 4 + 9 * MB_GLYPH_W) return glyph_color(fx_title(pat)[(x - 4) / MB_GLYPH_W]);
        return 0;
    }
    if (y == 14) return (x >= 4 && x <= 123) ? FX_SEP_COLOR : 0;
    if (x >= 125) return (x <= 126 && y < 15 + FX_THUMB_H) ? FX_THUMB_COLOR : 0;
    if (x < 3 || y >= 15 + 8 * 14) return 0;
    uint8_t r = (uint8_t)((y - 15) / 14), half = x <= 63 ? 0 : 1;
    if (r == row) half = (uint8_t)(1 - half);
    return fx_row_colors[pat][r][half];
}
static int f1_mismatches(uint8_t pat, uint8_t row) {
    int bad = 0;
    for (uint16_t y = 0; y < MB_H; y++)
        for (uint16_t x = 0; x < MB_W; x++)
            if (fb[y][x] != expect_f1(x, y, pat, row)) bad++;
    return bad;
}
static int f2_mismatches(void) {
    int bad = 0;
    for (uint16_t y = 0; y < MB_H; y++)
        for (uint16_t x = 0; x < MB_W; x++)
            if (fb[y][x] != fx_tile_colors[(y / 32) * 4 + x / 32]) bad++;
    return bad;
}

/* --- C1 ----------------------------------------------------------------------- */

static void to_done(void) {
    po_restore_advance();   /* not in CLEAR/STAGES: a no-op */
    while (po_phase() == RESTORE_CLEAR || po_phase() == RESTORE_STAGES) po_restore_advance();
    po_residual_in_t in = {0};
    CHECK(po_residual_next(&in, 0) == PO_RES_DONE);
}
static void boot_to_dash(void) {
    po_init();
    CHECK(po_phase() == RESTORE_SPLASH);
    CHECK(po_event(PO_EV_STARTUP, false, 0) & PO_ACT_RESTORE_START);
    to_done();
    CHECK(po_restored(po_gen()));
}

static void test_transitions(void) {
    uint16_t a;

    /* Boot: the startup restore runs its phases in order. */
    po_init();
    a = po_event(PO_EV_STARTUP, false, 0);
    CHECK(a == PO_ACT_RESTORE_START && po_phase() == RESTORE_CLEAR && po_restore_step() == 1);
    for (int i = 0; i < PO_CLEAR_BANDS; i++) po_restore_advance();
    CHECK(po_phase() == RESTORE_STAGES && po_restore_step() == PO_CLEAR_BANDS + 1);
    for (int i = 0; i < PO_STAGES; i++) po_restore_advance();
    CHECK(po_phase() == RESTORE_RESIDUAL && po_restoring());
    po_residual_in_t in = {0};
    CHECK(po_residual_next(&in, 0) == PO_RES_DONE && po_phase() == RESTORE_DONE);
    CHECK(po_dash_paints() && po_anim_admissible() && !po_owner_band_busy());

    /* DASH, NONE: the opener opens (no wake hold), with actions O. */
    a = po_event(PO_EV_OPENER, false, 0);
    CHECK(po_owner() == PANEL_MENU && po_session() == SESSION_OPEN);
    CHECK((a & (PO_ACT_QUIESCE_DROP | PO_ACT_RESET_BUFFERS | PO_ACT_OVERLAYS_OFF | PO_ACT_REPEAT_CANCEL |
                PO_ACT_MENU_CLEAR | PO_ACT_INPUT_CLEAR)) ==
          (PO_ACT_QUIESCE_DROP | PO_ACT_RESET_BUFFERS | PO_ACT_OVERLAYS_OFF | PO_ACT_REPEAT_CANCEL |
           PO_ACT_MENU_CLEAR | PO_ACT_INPUT_CLEAR));
    CHECK(po_phase() == RESTORE_WAITING);   /* leaving DASH invalidates DONE */
    CHECK(!po_restored(po_gen()) && po_visible() && po_sleep_blocked() && po_owner_band_busy());
    CHECK(po_panel_lit_for_owner() && !po_anim_admissible());

    /* MENU, OPEN: refusals. */
    CHECK(po_event(PO_EV_ANIM_START, false, 0) == PO_ACT_REFUSED);
    CHECK(po_event(PO_EV_DEBUG_CLICK, false, 0) == PO_ACT_REFUSED);
    CHECK(po_event(PO_EV_STARTUP, false, 0) == 0 && po_phase() == RESTORE_WAITING);

    /* Diagnostics > Health, then a click back; > Camera direct; DBG_PAGE cycles. */
    a = po_event(PO_EV_DIAG_HEALTH, false, 0);
    CHECK(po_owner() == PANEL_DEBUG && po_session() == SESSION_OPEN && po_debug_page() == DEBUG_PAGE_HEALTH);
    CHECK((a & PO_ACT_DEBUG_ENTER) && (a & PO_ACT_EDIT_CANCEL) && po_return_to_diag() && po_visible());
    a = po_event(PO_EV_DEBUG_CLICK, false, 0);
    CHECK(po_owner() == PANEL_MENU && (a & PO_ACT_MENU_CLEAR));
    a = po_event(PO_EV_DIAG_CAMERA, false, 0);
    CHECK(po_owner() == PANEL_DEBUG && po_debug_page() == DEBUG_PAGE_CAMERA);
    po_event(PO_EV_DEBUG_CLICK, false, 0);
    a = po_event(PO_EV_DBG_PAGE, false, 0);   /* MENU: into Health */
    CHECK(po_owner() == PANEL_DEBUG && po_debug_page() == DEBUG_PAGE_HEALTH);
    a = po_event(PO_EV_DBG_PAGE, false, 0);   /* Health to Camera in place */
    CHECK(a == PO_ACT_DEBUG_CAMERA && po_debug_page() == DEBUG_PAGE_CAMERA);
    a = po_event(PO_EV_DBG_PAGE, false, 0);   /* back to MENU at Diagnostics */
    CHECK(po_owner() == PANEL_MENU && po_session() == SESSION_OPEN);

    /* Close from DEBUG under the session: DASH, a restore started. */
    po_event(PO_EV_DIAG_HEALTH, false, 0);
    uint16_t g = po_gen();
    a = po_event(PO_EV_CLOSE, false, 0);
    CHECK(po_owner() == PANEL_DASH && po_session() == SESSION_NONE && po_phase() == RESTORE_CLEAR);
    CHECK((a & PO_ACT_RESTORE_START) && (a & PO_ACT_EDIT_CANCEL) && (a & PO_ACT_OVERLAYS_REPRIME));
    CHECK(po_gen() == (uint16_t)(g + 1) && !po_visible() && !po_sleep_blocked());
    CHECK(po_event(PO_EV_CLOSE, false, 0) == PO_ACT_REFUSED);

    /* Standalone DEBUG: today's three-step cycle, and leaving DONE invalid. */
    boot_to_dash();
    g = po_gen();
    a = po_event(PO_EV_DBG_PAGE, false, 0);
    CHECK(po_owner() == PANEL_DEBUG && po_session() == SESSION_NONE && po_phase() == RESTORE_WAITING);
    CHECK(!po_restored(g) && po_panel_lit_for_owner());
    CHECK(po_event(PO_EV_DBG_PAGE, false, 0) == PO_ACT_DEBUG_CAMERA);
    a = po_event(PO_EV_DBG_PAGE, false, 0);
    CHECK(po_owner() == PANEL_DASH && (a & PO_ACT_RESTORE_START) && po_phase() == RESTORE_CLEAR);
    to_done();

    /* A standalone DEBUG hands off to the menu on the opener. */
    po_event(PO_EV_DBG_PAGE, false, 0);
    a = po_event(PO_EV_OPENER, false, 0);
    CHECK(po_owner() == PANEL_MENU && po_session() == SESSION_OPEN && (a & PO_ACT_MENU_CLEAR));
    po_event(PO_EV_CLOSE, false, 0);
    to_done();

    /* PENDING: the wake hold defers the opening, and the dashboard keeps painting. */
    a = po_event(PO_EV_OPENER, true, 0);
    CHECK(po_session() == SESSION_PENDING && po_owner() == PANEL_DASH);
    CHECK(a == (PO_ACT_OVERLAYS_OFF | PO_ACT_INPUT_CLEAR));
    CHECK(!po_visible() && po_sleep_blocked() && po_dash_paints() && po_owner_band_busy());
    CHECK(po_event(PO_EV_DBG_PAGE, false, 0) == PO_ACT_REFUSED);
    CHECK(po_event(PO_EV_ANIM_START, false, 0) == PO_ACT_REFUSED);
    a = po_event(PO_EV_WAKE_RELEASED, false, 0);
    CHECK(po_session() == SESSION_OPEN && po_owner() == PANEL_MENU && (a & PO_ACT_MENU_CLEAR));
    po_event(PO_EV_CLOSE, false, 0);
    to_done();

    /* PENDING cancelled by a second opener; a startup request during it runs. */
    po_event(PO_EV_OPENER, true, 0);
    a = po_event(PO_EV_STARTUP, false, 0);
    CHECK((a & PO_ACT_RESTORE_START) && po_phase() == RESTORE_CLEAR);   /* not WAITING: the owner is DASH */
    a = po_event(PO_EV_OPENER, true, 0);
    CHECK(po_session() == SESSION_NONE && (a & PO_ACT_OVERLAYS_REPRIME));
    CHECK(po_phase() == RESTORE_CLEAR);   /* its work goes on */
    to_done();

    /* The animation: admitted only from DASH, NONE, DONE; its stop always. */
    a = po_event(PO_EV_ANIM_START, false, 0);
    CHECK(po_owner() == PANEL_ANIM && (a & PO_ACT_ANIM_START) && po_phase() == RESTORE_WAITING);
    CHECK(!po_panel_lit_for_owner());
    a = po_event(PO_EV_OPENER, false, 0);
    CHECK(a == PO_ACT_REFUSED && po_owner() == PANEL_ANIM);
    CHECK(po_event(PO_EV_DBG_PAGE, false, 0) == PO_ACT_REFUSED);
    a = po_event(PO_EV_STARTUP, false, 0);   /* the startup callback under ANIM: WAITING */
    CHECK(a == 0 && po_phase() == RESTORE_WAITING);
    g = po_gen();
    a = po_event(PO_EV_ANIM_STOP, false, 0);
    CHECK(po_owner() == PANEL_DASH && (a & PO_ACT_ANIM_STOP) && (a & PO_ACT_RESTORE_START));
    CHECK(po_gen() == (uint16_t)(g + 1) && po_restore_step() == 1);   /* from band 1 */
    CHECK(po_event(PO_EV_ANIM_STOP, false, 0) == PO_ACT_REFUSED);
    CHECK(po_event(PO_EV_ANIM_START, false, 0) == PO_ACT_REFUSED);   /* not until DONE */
    to_done();

    /* A wake while OPEN: recorded, and the session closes when the hold lifts. */
    po_event(PO_EV_OPENER, false, 0);
    CHECK(po_event(PO_EV_WAKE_WHILE_OPEN, false, 0) == 0);
    CHECK(po_invariant_fail() & PO_FAIL_WAKE_OPEN);
    a = po_event(PO_EV_WAKE_RELEASED, false, 0);
    CHECK(po_session() == SESSION_NONE && (a & PO_ACT_RESTORE_START));
}

static void test_restore_residual_and_loss(void) {
    boot_to_dash();
    po_residual_in_t in = {0};

    /* The scheduler's order, one thing a pass. */
    po_event(PO_EV_STARTUP, false, 0);
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    in.busy = in.lq = in.gq = in.batt = in.logo_os = in.logo_conn = true;
    CHECK(po_residual_next(&in, 0) == PO_RES_RECOVER);
    in.busy = false;  CHECK(po_residual_next(&in, 0) == PO_RES_LQ);
    in.lq = false;    CHECK(po_residual_next(&in, 0) == PO_RES_GQ);
    in.gq = false;    CHECK(po_residual_next(&in, 0) == PO_RES_BATT);
    in.batt = false;  CHECK(po_residual_next(&in, 0) == PO_RES_LOGO_OS);
    in.logo_os = false; CHECK(po_residual_next(&in, 0) == PO_RES_LOGO_CONN);
    in.logo_conn = false; in.lost = true;
    CHECK(po_residual_next(&in, 0) == PO_RES_WAIT && po_phase() == RESTORE_RESIDUAL);   /* never DONE over a loss */
    in.lost = false;
    CHECK(po_residual_next(&in, 0) == PO_RES_DONE && po_dash_paints());
    CHECK(po_residual_next(&in, 0) == PO_RES_NONE);

    /* A loss during the restore: damaged; RESIDUAL restarts instead of DONE. */
    uint16_t g = po_gen();
    po_event(PO_EV_STARTUP, false, 1000);
    po_restore_advance();
    CHECK(po_loss(1000) == 0 && po_damaged());
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    CHECK(po_residual_next(&in, 1000) == PO_RES_RESTART);   /* the first repair is immediate */
    CHECK(po_gen() == (uint16_t)(g + 2) && po_phase() == RESTORE_CLEAR && !po_damaged());
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    CHECK(po_residual_next(&in, 1100) == PO_RES_DONE);

    /* Two losses under 5 s apart, the first repair DONE before the second:
     * the second is remembered at once and repaired after the cooldown. */
    g = po_gen();
    CHECK(po_loss(2000) == 0 && po_phase() == RESTORE_RESIDUAL && po_damaged());
    CHECK(!po_restored(g));                                     /* false from this pass */
    CHECK(!po_dash_paints());
    CHECK(po_residual_next(&in, 2000) == PO_RES_WAIT);          /* 1000 ms since the last repair */
    CHECK(po_residual_next(&in, 5999) == PO_RES_WAIT);
    CHECK(po_residual_next(&in, 6000) == PO_RES_RESTART);
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    CHECK(po_residual_next(&in, 6001) == PO_RES_DONE);
    CHECK(po_loss(6500) == 0);
    CHECK(po_residual_next(&in, 6500) == PO_RES_WAIT);          /* within the cooldown again */
    CHECK(po_residual_next(&in, 11000) == PO_RES_RESTART);
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    CHECK(po_residual_next(&in, 11000) == PO_RES_DONE);

    /* The other owners' handlers. */
    po_event(PO_EV_OPENER, false, 0);
    CHECK(po_loss(0) == PO_ACT_RESET_BUFFERS);
    po_event(PO_EV_DIAG_CAMERA, false, 0);
    CHECK(po_loss(0) == PO_ACT_DEBUG_ENTER && po_debug_page() == DEBUG_PAGE_CAMERA);
    po_event(PO_EV_CLOSE, false, 0);
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    CHECK(po_residual_next(&in, 20000) == PO_RES_DONE);
    po_event(PO_EV_ANIM_START, false, 0);
    CHECK(po_loss(0) == PO_ACT_ANIM_STOP);
    CHECK(po_event(PO_EV_ANIM_STOP, false, 0) & PO_ACT_RESTORE_START);

    /* A loss in SPLASH or WAITING is nothing to repair. */
    po_init();
    CHECK(po_loss(0) == 0 && !po_damaged() && po_phase() == RESTORE_SPLASH);
}

/* --- C2 ----------------------------------------------------------------------- */

static void test_input(void) {
    int8_t     t;
    mi_latch_t l;

    mi_init();
    /* Session NONE: an uncaptured knob is forwarded both ways; the opener is captured. */
    CHECK(mi_physical(MI_KNOB, true, false, true, SESSION_NONE, 0) == MI_FORWARD);
    CHECK(mi_physical(MI_KNOB, false, false, true, SESSION_NONE, 10) == MI_FORWARD);
    CHECK(mi_physical(MI_CW, true, true, true, SESSION_NONE, 0) == MI_FORWARD);   /* Fn plus a turn isn't the opener */
    CHECK(mi_physical(MI_CW, false, true, true, SESSION_NONE, 0) == MI_FORWARD);
    CHECK(mi_physical(MI_KNOB, true, true, false, SESSION_NONE, 0) == MI_FORWARD); /* not enabled */
    CHECK(mi_physical(MI_KNOB, false, true, false, SESSION_NONE, 0) == MI_FORWARD);
    CHECK(mi_physical(MI_KNOB, true, true, true, SESSION_NONE, 0) == MI_OPENER);
    CHECK(mi_capture_bits() == 1u);
    /* Its release, with Fn already up and the session now open: consumed, no click. */
    CHECK(mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 50) == MI_CONSUMED);
    CHECK(mi_capture_bits() == 0 && !mi_take(&t, &l));

    /* A forwarded press whose release comes after a session opened: forwarded. */
    CHECK(mi_physical(MI_KNOB, true, false, true, SESSION_NONE, 0) == MI_FORWARD);
    CHECK(mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 10) == MI_FORWARD);
    CHECK(mi_physical(MI_CW, true, false, true, SESSION_NONE, 0) == MI_FORWARD);
    CHECK(mi_physical(MI_CW, false, false, true, SESSION_OPEN, 0) == MI_FORWARD);

    /* OPEN: the hold's boundary at 599, 600 and 601 ms. */
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 1000);
    mi_tick(1599);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 1599);
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLICK);
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 2000);
    mi_tick(2600);
    CHECK(mi_latch() == MI_LATCH_BACK);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 2601);
    CHECK(mi_take(&t, &l) && l == MI_LATCH_BACK && !mi_take(&t, &l));   /* exactly once */
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 3000);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 3601);       /* the tick missed it */
    CHECK(mi_take(&t, &l) && l == MI_LATCH_BACK);

    /* A hold across a close: the gesture ends, the release is still consumed. */
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 4000);
    mi_clear();
    mi_tick(4700);
    CHECK(mi_latch() == MI_LATCH_NONE);
    CHECK(mi_physical(MI_KNOB, false, false, true, SESSION_NONE, 4800) == MI_CONSUMED);
    CHECK(!mi_take(&t, &l));

    /* Turns, a latch freezing them, precedence, saturation, close discarding. */
    mi_init();
    for (int i = 0; i < 3; i++) {
        mi_physical(MI_CW, true, false, true, SESSION_OPEN, 0);
        mi_physical(MI_CW, false, false, true, SESSION_OPEN, 0);
    }
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 0);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 100);   /* click */
    mi_physical(MI_CCW, true, false, true, SESSION_OPEN, 0);       /* after the latch: dropped */
    mi_physical(MI_CCW, false, false, true, SESSION_OPEN, 0);
    CHECK(mi_turns() == 3 && mi_dropped() == 1);
    CHECK(mi_take(&t, &l) && t == 3 && l == MI_LATCH_CLICK);
    mi_physical(MI_KNOB, true, true, true, SESSION_OPEN, 0);       /* Fn plus a click: close */
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 50);
    CHECK(mi_latch() == MI_LATCH_CLOSE);
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLOSE && t == 0);
    mi_init();
    for (int i = 0; i < 70; i++) mi_physical(MI_CW, true, false, true, SESSION_OPEN, 0), mi_physical(MI_CW, false, false, true, SESSION_OPEN, 0);
    CHECK(mi_turns() == MI_TURNS_MAX && mi_dropped() == 6);
    mi_physical(MI_KNOB, true, true, true, SESSION_OPEN, 0);
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLOSE && t == 0);       /* close discards them */
    mi_physical(MI_KNOB, false, false, true, SESSION_NONE, 0);

    /* PENDING: knob input captured and discarded; a second opener returned. */
    mi_init();
    CHECK(mi_physical(MI_CW, true, false, true, SESSION_PENDING, 0) == MI_CONSUMED);
    CHECK(mi_physical(MI_CW, false, false, true, SESSION_NONE, 0) == MI_CONSUMED);
    CHECK(mi_turns() == 0);
    CHECK(mi_physical(MI_KNOB, true, true, true, SESSION_PENDING, 0) == MI_OPENER);
    CHECK(mi_physical(MI_KNOB, false, true, true, SESSION_NONE, 0) == MI_CONSUMED);

    /* The idle timer counts knob input only. */
    mi_physical(MI_CW, true, false, true, SESSION_OPEN, 777);
    CHECK(mi_last_input() == 777);
}

static void test_op27_flight(void) {
    int8_t     t;
    mi_latch_t l;
    uint8_t    s1, s2;

    mi_init();
    CHECK(mi_last_seq() == 0 && mi_last_state() == MI_ST_NONE);
    CHECK(mi_begin(MI_KIND_CLICK, &s1) == MI_OK && s1 == 1);
    CHECK(mi_begin(MI_KIND_TURNS, &s2) == MI_BUSY);   /* single flight */
    CHECK(mi_last_seq() == 1 && mi_last_state() == MI_ST_PENDING);   /* a busy reply left it alone */
    mi_syn_click();
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLICK);
    CHECK(mi_last_state() == MI_ST_DONE && mi_outstanding() == MI_KIND_NONE);

    /* Turns, then cleared at a handoff before the screen took them: cancelled. */
    mi_begin(MI_KIND_TURNS, &s1);
    mi_syn_turns(5);
    mi_clear();
    CHECK(mi_last_seq() == s1 && mi_last_state() == MI_ST_CANCELLED);

    /* A hold: done after its release is taken; 650 ms gives Back. */
    mi_begin(MI_KIND_HOLD, &s1);
    CHECK(mi_syn_hold(650, 100) == MI_OK);
    mi_tick(699);
    CHECK(mi_latch() == MI_LATCH_NONE && mi_last_state() == MI_ST_PENDING);
    mi_tick(700);
    CHECK(mi_latch() == MI_LATCH_BACK && mi_last_state() == MI_ST_PENDING);   /* not until its release */
    mi_tick(750);
    CHECK(!mi_syn_hold_active());
    CHECK(mi_take(&t, &l) && l == MI_LATCH_BACK && mi_last_state() == MI_ST_DONE);

    /* A short synthetic hold is a click. */
    mi_begin(MI_KIND_HOLD, &s1);
    mi_syn_hold(100, 0);
    mi_tick(100);
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLICK && mi_last_state() == MI_ST_DONE);

    /* A physical press cancels a synthetic hold, with no Back. */
    mi_begin(MI_KIND_HOLD, &s1);
    mi_syn_hold(1000, 0);
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 10);
    CHECK(mi_last_state() == MI_ST_CANCELLED && !mi_syn_hold_active());
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 100);
    mi_tick(2000);   /* the synthetic hold's 600 ms and release would both be past */
    CHECK(mi_take(&t, &l) && l == MI_LATCH_CLICK);   /* only the physical click */
    /* While the physical knob is down, a synthetic hold is refused. */
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 3000);
    CHECK(mi_knob_down() && mi_syn_hold(650, 3000) == MI_BUSY);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 3020);
    mi_take(&t, &l);

    /* The sequence wraps past 255 and never reads 0. */
    for (int i = 0; i < 300; i++) {
        CHECK(mi_begin(MI_KIND_RESTORE, &s1) == MI_OK && s1 != 0);
        mi_finish(MI_ST_DONE);
    }
    /* Synthetic turns behind a physical latch are superseded. */
    mi_physical(MI_KNOB, true, false, true, SESSION_OPEN, 0);
    mi_physical(MI_KNOB, false, false, true, SESSION_OPEN, 10);
    mi_begin(MI_KIND_TURNS, &s1);
    mi_syn_turns(2);
    CHECK(mi_last_state() == MI_ST_SUPERSEDED && mi_turns() == 0);
}

/* --- C3 and C9 ------------------------------------------------------------------ */

static void test_fixture_paint(void) {
    fake_reset();
    ms_init();
    fx_open();
    CHECK(ms_clearing() && fx_screen() == FX_SCREEN_F1);
    int passes = run_until_settled(200);
    CHECK(passes > 0 && bands_ok == MB_BANDS);
    CHECK(f1_mismatches(0, 0) == 0);
    CHECK(ms_unsettled() == 0);

    /* A, then B stopped after n, then A again: correct for every n. */
    for (uint8_t n = 1; n < FX_F1_OPS; n++) {
        fx_set_pattern(1);
        ms_stop_after(n);
        int guard = 0;
        while (!ms_stopped() && guard++ < 200) pass();
        CHECK(ms_stopped() && ms_ops() == n);
        CHECK(!ms_settled());
        fx_set_pattern(0);
        CHECK(run_until_settled(200) > 0);
        CHECK(f1_mismatches(0, 0) == 0);
    }
    /* A full B is 27 operations. */
    fx_set_pattern(1);
    CHECK(run_until_settled(200) > 0 && ms_ops() == FX_F1_OPS && f1_mismatches(1, 0) == 0);

    /* A selection change on unchanged text repaints both rows, nothing else. */
    uint8_t before = ms_ops();
    (void)before;
    fx_input(1, MI_LATCH_NONE);
    CHECK(ms_unsettled() == 2);
    CHECK(run_until_settled(50) > 0 && ms_ops() == 4 && f1_mismatches(1, 1) == 0);

    /* The bus busy for a glyph: the same chunk is retried. */
    fx_set_pattern(0);
    bus_busy_once = true;
    CHECK(run_until_settled(200) > 0 && f1_mismatches(0, 1) == 0);

    /* A loss during a glyph: every slot invalid, everything repainted. */
    fx_set_pattern(1);
    fault_next_dma = 1;
    CHECK(run_until_settled(300) > 0 && f1_mismatches(1, 1) == 0);

    /* The other layout, and a navigation during its clear: the clear finishes. */
    fx_other_layout();
    pass(); pass();
    CHECK(ms_clearing());
    fx_other_layout();   /* back to F1 mid-clear */
    CHECK(ms_clearing());
    CHECK(run_until_settled(300) > 0 && f1_mismatches(1, FX_ROW_F2) == 0);
    fx_other_layout();
    CHECK(run_until_settled(300) > 0 && f2_mismatches() == 0 && fx_screen() == FX_SCREEN_F2);

    /* A failed band is retried, the cursor not advanced: no stale pixel survives. */
    fx_other_layout();
    fault_next_band = 2;
    bands_ok = 0;
    CHECK(run_until_settled(300) > 0 && bands_ok == MB_BANDS);
    CHECK(f1_mismatches(1, FX_ROW_F2) == 0);

    /* Input: the clicks' destinations. */
    while (fx_cursor() != 0) fx_input(1, MI_LATCH_NONE);
    CHECK(fx_input(0, MI_LATCH_CLICK) == FX_NONE && fx_pattern() == 0);   /* row 0 toggles */
    CHECK(fx_input(-2, MI_LATCH_NONE) == FX_NONE && fx_cursor() == 6);    /* wraps */
    CHECK(fx_input(0, MI_LATCH_CLICK) == FX_NONE && fx_screen() == FX_SCREEN_F2);
    CHECK(fx_input(3, MI_LATCH_CLICK) == FX_NONE && fx_screen() == FX_SCREEN_F1 && fx_cursor() == FX_ROW_F2);
    CHECK(fx_input(1, MI_LATCH_CLICK) == FX_DIAG);
    fx_return_from_diag();
    CHECK(fx_cursor() == FX_ROW_DIAG && ms_clearing());
    CHECK(run_until_settled(300) > 0 && f1_mismatches(fx_pattern(), FX_ROW_DIAG) == 0);
    CHECK(fx_input(0, MI_LATCH_BACK) == FX_CLOSE && fx_input(0, MI_LATCH_CLOSE) == FX_CLOSE);

    /* Pattern changes need F1. */
    fx_other_layout();
    CHECK(!fx_set_pattern(1));
}

int main(void) {
    test_transitions();
    test_restore_residual_and_loss();
    test_input();
    test_op27_flight();
    test_fixture_paint();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("menu S0: all checks passed\n");
    return 0;
}
