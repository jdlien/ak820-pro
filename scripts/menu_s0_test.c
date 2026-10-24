/* Host test of the configuration menu's S0 foundations: the owner, session and
 * restore (menu/panel_owner.c), the knob's capture and op 27's single flight
 * (menu/menu_input.c), the damage model (menu/menu_slots.c), the fixture
 * (menu/menu_fixture.c), and the task, op 27 and the menu's side of an owner
 * event (menu/menu_ops.c), against a fake framebuffer and environment. These are the firmware's
 * own files: plans/CONFIG-MENU-BUILD-PLAN.md, "S0". Build and run:
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -DMENU_HOST_TEST -I $D/menu scripts/menu_s0_test.c \
 *       $D/menu/panel_owner.c $D/menu/menu_input.c $D/menu/menu_slots.c \
 *       $D/menu/menu_fixture.c $D/menu/menu_ops.c -o ms0 && ./ms0
 *
 * (On Windows, mingw64's gcc first on PATH: CLAUDE.md.) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "menu_backend.h"
#include "menu_fixture.h"
#include "menu_input.h"
#include "menu_slots.h"
#include "panel_owner.h"
#include "menu_env.h"
#include "menu_ops.h"
#include "menu_text.h"
#include "../graphics/res/font_small_mono.h"   /* through -I $D/menu */

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* --- the fake panel ----------------------------------------------------------
 * A glyph is a DMA: it arms (busy) and lands at the next pass's start, or is
 * lost if a fault was injected. A glyph's cell is painted as one colour, the
 * character's code, which is all the frames need to tell glyphs apart; which
 * pixels are a glyph's is kept apart in `is_glyph`, since a code can equal a
 * fixture colour (0x8010 is both). */
static uint16_t fb[MB_H][MB_W];
static bool     is_glyph[MB_H][MB_W];
static bool     dma_busy;
static uint16_t dma_x, dma_y, dma_col;
static bool     lost_latched;
static int      fault_next_dma;     /* the next N transfers are given up */
static int      fault_next_band;    /* the next N clear bands fail */
static bool     bus_busy_once;      /* the next glyph finds the bus busy */
static int      fault_next_fill;    /* the next N fills give up, as a polled send does: a loss */
static bool     fault_fill_prefix;  /* ...after painting their first half of rows (HC_POLLFAULT's mode 0) */
static int      glyph_ops, fill_ops, bands_ok;
static uint32_t pass_bytes, max_pass_bytes;
static uint32_t fake_ticks;   /* C10's clock: a pass is 1,000 ticks (5.3 ms), a fill 300 more */   /* CPU-fed pixels in the current pass, and the most in any (C4) */

static void paint_fb(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t c, bool glyph) {
    for (uint16_t y = y0; y <= y1 && y < MB_H; y++)
        for (uint16_t x = x0; x <= x1 && x < MB_W; x++) {
            fb[y][x]       = c;
            is_glyph[y][x] = glyph;
        }
}
static void fill_fb(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t c) {
    paint_fb(x0, y0, x1, y1, c, false);
}
static uint16_t glyph_color(char c) { return (uint16_t)(0x8000u | (uint8_t)c); }

/* The pass boundary: an armed DMA completes, or is given up, its end timed
 * as the ISR times it. */
static uint32_t fake_dma_end;
static void dma_settle(void) {
    if (!dma_busy) return;
    dma_busy     = false;
    fake_dma_end = fake_ticks;
    if (fault_next_dma > 0) {
        fault_next_dma--;
        lost_latched = true;
        return;
    }
    paint_fb(dma_x, dma_y, (uint16_t)(dma_x + MB_GLYPH_W - 1), (uint16_t)(dma_y + MB_GLYPH_H - 1), dma_col, true);
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
bool mb_fill(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t c) {
    dma_settle();   /* bus_quiesce */
    pass_bytes += (uint32_t)(x1 - x0 + 1) * (uint32_t)(y1 - y0 + 1) * 2u;
    if (fault_next_fill > 0) {
        fault_next_fill--;
        if (fault_fill_prefix && y1 > y0) fill_fb(x0, y0, x1, (uint16_t)(y0 + (y1 - y0) / 2u), c);
        lost_latched = true;   /* spi0_poll_send's give-up sets blit_lost */
        return false;
    }
    fill_fb(x0, y0, x1, y1, c);
    fill_ops++;
    fake_ticks += 300;
    return true;
}
bool mb_glyph(char c, uint16_t x, uint16_t y) {
    if (bus_busy_once) { bus_busy_once = false; return false; }
    if (dma_busy) return false;
    dma_busy = true;
    dma_x = x; dma_y = y; dma_col = glyph_color(c);
    glyph_ops++;
    return true;
}
static int mono_ops;
bool mb_mono(const uint8_t *bits, uint8_t stride, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t fg, uint16_t bg) {
    dma_settle();   /* the stream quiesces */
    pass_bytes += (uint32_t)w * h * 2u;
    uint16_t rows = h;
    bool     ok   = true;
    if (fault_next_fill > 0) {   /* a polled send gives up, as for a fill */
        fault_next_fill--;
        rows = fault_fill_prefix ? (uint16_t)(h / 2u) : 0;
        lost_latched = true;
        ok           = false;
    }
    for (uint16_t r = 0; r < rows; r++)
        for (uint16_t c = 0; c < w; c++) {
            bool ink                   = (bits[r * stride + c / 8] >> (7 - c % 8)) & 1;
            fb[y + r][x + c]       = ink ? fg : bg;
            is_glyph[y + r][x + c] = false;
        }
    if (ok) mono_ops++;
    fake_ticks += 300;
    return ok;
}
bool mb_busy(void) { return dma_busy; }
bool mb_lost_pending(void) { return lost_latched; }
uint32_t mb_now_ticks(void) { return fake_ticks; }
uint32_t mb_dma_end_ticks(void) { return fake_dma_end; }
static bool take_lost(void) { bool l = lost_latched; lost_latched = false; return l; }

static void fake_reset(void) {
    memset(fb, 0x55, sizeof fb);   /* not black: a pixel the clear missed shows */
    memset(is_glyph, 0, sizeof is_glyph);
    dma_busy = lost_latched = bus_busy_once = false;
    fault_next_dma = fault_next_band = fault_next_fill = 0;
    fault_fill_prefix = false;
    glyph_ops = fill_ops = bands_ok = mono_ops = 0;
    pass_bytes = max_pass_bytes = 0;
}

/* One pass of the menu's painter, as the pump runs it: the DMA's completion
 * first, the loss taken at the top, then one bounded operation. */
static ms_step_t pass(void) {
    fake_ticks += 1000;
    dma_settle();
    if (take_lost()) fx_invalidate();
    pass_bytes = 0;
    ms_step_t s = ms_step();
    if (pass_bytes > max_pass_bytes) max_pass_bytes = pass_bytes;
    return s;
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
    if (y == 14) return (x >= 4 && x <= 123) ? fx_sep_colors[pat] : 0;
    if (x >= 125) {   /* C8's scrollbar: x 125, y 15-126 */
        if (x != 125 || y > 126) return 0;
        return y < 15 + FX_THUMB_H ? fx_thumb_colors[pat] : fx_track_colors[pat];
    }
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
/* The expected F3 frame (S1's mono text), from the face itself rather than
 * menu_text.c: the title and rows' cells from x 4, the inverted row's pad at
 * x 3, x 124 black, the separator, the scrollbar. */
static uint16_t expect_f3(uint16_t x, uint16_t y, uint8_t style, uint8_t row) {
    const bool inv = (style & FX_MONO_INV) != 0;
    if (y == 14) return (x >= 4 && x <= 123) ? FX_MONO_GREY : 0;
    if (x == 125) {
        if (y < 15 || y > 126) return 0;
        return y < 15 + FX_THUMB_H ? FX_MONO_WHITE : FX_MONO_TRACK;
    }
    if (x < 3 || x > 124 || y >= 15 + 8 * 14) return 0;
    const char *s;
    uint16_t    fg = FX_MONO_WHITE, bg = FX_MONO_BLACK, gy;
    if (y < 14) {
        s  = fx_mono_titles[style];
        gy = y;
    } else {
        uint8_t r   = (uint8_t)((y - 15) / 14);
        bool    sel = r == row;
        s           = fx_mono_rows[r];
        gy          = (uint16_t)((y - 15) % 14);
        if (inv && sel) { fg = FX_MONO_BLACK; bg = FX_MONO_WHITE; }
        else if (!inv) fg = sel ? FX_MONO_LIT : FX_MONO_DIM;
    }
    if (x == 3) return bg;
    if (x == 124) return FX_MONO_BLACK;   /* ink on the inverted row, background elsewhere: black either way */
    size_t        cell = (size_t)(x - 4) / 6, len = strlen(s);
    uint8_t       code = cell < len ? (uint8_t)s[cell] : (uint8_t)' ';
    const uint8_t *g   = code >= 0x80 ? font_small_mono[FONT_MONO_ASCII + code - 0x80] : font_small_mono[code - 0x20];
    return (g[gy] & (0x80 >> ((x - 4) % 6))) ? fg : bg;
}
static int f3_mismatches(uint8_t style, uint8_t row) {
    int bad = 0;
    for (uint16_t y = 0; y < MB_H; y++)
        for (uint16_t x = 0; x < MB_W; x++)
            if (fb[y][x] != expect_f3(x, y, style, row) || is_glyph[y][x]) bad++;
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
        ms_stop_release();   /* as op 27's next sub 0 does */
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

/* --- S1: the pieces under MB_PASS_BYTES, and the op's end (C4, revision 9) ----- */

/* A settled A on F1, cursor at row 0. */
static void settled_a(void) {
    fake_reset();
    ms_init();
    fx_open();
    CHECK(run_until_settled(400) > 0 && f1_mismatches(0, 0) == 0);
}

static void test_pieces(void) {
    /* No pass sends more than the budget: F1 from a fresh open, then F2. */
    settled_a();
    CHECK(max_pass_bytes > 0 && max_pass_bytes <= MB_PASS_BYTES);
    fx_other_layout();
    CHECK(run_until_settled(400) > 0 && f2_mismatches() == 0);
    CHECK(max_pass_bytes <= MB_PASS_BYTES);

    /* Still C9's 27 logical ops for a full B, and 4 for a selection change. */
    settled_a();
    fx_set_pattern(1);
    int full = run_until_settled(400);
    CHECK(full > 0 && ms_ops() == FX_F1_OPS && f1_mismatches(1, 0) == 0);
    fx_input(1, MI_LATCH_NONE);
    CHECK(run_until_settled(100) > 0 && ms_ops() == 4 && f1_mismatches(1, 1) == 0);

    /* A retarget at every piece boundary of a B repaint: the frame ends right. */
    for (int k = 0; k < full; k++) {
        settled_a();
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        fx_set_pattern(0);
        CHECK(run_until_settled(400) > 0 && f1_mismatches(0, 0) == 0);
    }
    /* A selection change at every piece boundary of a B repaint. */
    for (int k = 0; k < full; k++) {
        settled_a();
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        fx_input(3, MI_LATCH_NONE);
        CHECK(run_until_settled(400) > 0 && f1_mismatches(1, 3) == 0);
    }
    /* A fill given up at every point of a B repaint, with nothing painted
     * and with a prefix painted: the loss repaints all, and the fault was
     * really taken. */
    int consumed = 0;
    for (int prefix = 0; prefix < 2; prefix++)
        for (int k = 0; k < full; k++) {
            settled_a();
            fx_set_pattern(1);
            for (int i = 0; i < k; i++) pass();
            fault_next_fill   = 1;
            fault_fill_prefix = prefix;
            CHECK(run_until_settled(800) > 0 && f1_mismatches(1, 0) == 0);
            if (fault_next_fill == 0) consumed++;   /* late k: no fill was left to fail */
            fault_next_fill = 0;
        }
    CHECK(consumed >= 2 * 4 * 2 * FX_ROWS);
    /* A fresh opening, and a return from another owner, at every piece
     * boundary of a B repaint. */
    for (int k = 0; k < full; k++) {
        settled_a();
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        fx_open();
        CHECK(run_until_settled(400) > 0 && f1_mismatches(0, 0) == 0);
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        fx_return_from_diag();
        CHECK(run_until_settled(400) > 0 && f1_mismatches(1, FX_ROW_DIAG) == 0);
    }
    /* F2: a layout change at every piece boundary of its tiles. */
    settled_a();
    fx_other_layout();
    int f2full = run_until_settled(400);
    CHECK(f2full > 0);
    for (int k = 0; k < f2full; k++) {
        settled_a();
        fx_other_layout();
        for (int i = 0; i < k; i++) pass();
        fx_other_layout();   /* back to F1 */
        CHECK(run_until_settled(400) > 0 && f1_mismatches(0, FX_ROW_F2) == 0);
    }
}

/* --- S1: the mono text on F3 (menu_text.c through mb_mono) ------------------- */

static int mono_full_ops(uint8_t style) { return style & FX_MONO_FULL ? 1 + 1 + FX_ROWS + 1 : 2 + 1 + 2 * FX_ROWS + 1; }

static void test_mono(void) {
    /* Each style from a settled F1: a layout change, its clear, the frame. */
    for (uint8_t st = 0; st < FX_MONO_STYLES; st++) {
        settled_a();
        max_pass_bytes = 0;
        int g = glyph_ops;
        fx_set_mono(st);
        CHECK(ms_clearing() && fx_screen() == FX_SCREEN_F3 && fx_pattern() == FX_MONO_FIRST + st);
        CHECK(run_until_settled(400) > 0 && f3_mismatches(st, 0) == 0);
        CHECK(max_pass_bytes > 0 && max_pass_bytes <= MB_PASS_BYTES);
        CHECK(ms_ops() == mono_full_ops(st));
        CHECK(glyph_ops == g);   /* F3 sends no flash glyph */
    }
    /* Styles within F3: a retarget, no clear; the title and the rows repaint,
     * the separator and the scrollbar don't. */
    settled_a();
    fx_set_mono(0);
    CHECK(run_until_settled(400) > 0);
    int g0 = glyph_ops;
    for (uint8_t st = 1; st <= FX_MONO_STYLES; st++) {
        uint8_t s = st % FX_MONO_STYLES;
        bands_ok  = 0;
        fx_set_mono(s);
        CHECK(!ms_clearing());
        CHECK(run_until_settled(400) > 0 && f3_mismatches(s, 0) == 0 && bands_ok == 0);
        CHECK(ms_ops() == mono_full_ops(s) - 2);
    }
    CHECK(glyph_ops == g0);
    /* A selection change: two rows, each 2 ops in half rows and 1 in full. */
    for (uint8_t st = 0; st < FX_MONO_STYLES; st++) {
        fx_set_mono(st);
        CHECK(run_until_settled(400) > 0);
        max_pass_bytes = 0;
        fx_input(1, MI_LATCH_NONE);
        CHECK(ms_unsettled() == 2);
        CHECK(run_until_settled(100) > 0 && ms_ops() == (st & FX_MONO_FULL ? 2 : 4));
        CHECK(f3_mismatches(st, fx_cursor()) == 0 && max_pass_bytes <= MB_PASS_BYTES);
    }
    /* At every piece boundary of a style's repaint: a selection change, a
     * style change, and a mono send given up (nothing sent, then half): the
     * frame ends right, and the fault was really taken. */
    for (uint8_t st = 0; st < FX_MONO_STYLES; st++) {
        settled_a();
        fx_set_mono((uint8_t)(st + 1));
        CHECK(run_until_settled(400) > 0);
        fx_set_mono(st);
        int full = run_until_settled(400);
        CHECK(full > 0);
        int consumed = 0;
        for (int k = 0; k < full; k++) {
            fx_set_mono((uint8_t)(st + 1));
            CHECK(run_until_settled(400) > 0);
            fx_set_mono(st);
            for (int i = 0; i < k; i++) pass();
            fx_input(3, MI_LATCH_NONE);
            CHECK(run_until_settled(400) > 0 && f3_mismatches(st, fx_cursor()) == 0);

            fx_set_mono((uint8_t)(st + 1));
            for (int i = 0; i < k; i++) pass();
            fx_set_mono(st);
            CHECK(run_until_settled(400) > 0 && f3_mismatches(st, fx_cursor()) == 0);

            for (int prefix = 0; prefix < 2; prefix++) {
                fx_set_mono((uint8_t)(st + 1));
                for (int i = 0; i < k; i++) pass();
                fault_next_fill   = 1;
                fault_fill_prefix = prefix;
                CHECK(run_until_settled(800) > 0 && f3_mismatches((uint8_t)((st + 1) % FX_MONO_STYLES), fx_cursor()) == 0);
                if (fault_next_fill == 0) consumed++;
                fault_next_fill = 0;
                fx_set_mono(st);
                CHECK(run_until_settled(400) > 0);
            }
        }
        CHECK(consumed >= full);
    }
    /* Input on F3: turns move the row, a click on rows 0-5 is the next style,
     * row 6 goes to F2 and back to F1, row 7 is Diagnostics. */
    settled_a();
    fx_set_mono(0);
    CHECK(run_until_settled(400) > 0);
    CHECK(fx_input(2, MI_LATCH_CLICK) == FX_NONE && fx_cursor() == 2 && fx_pattern() == FX_MONO_FIRST + 1);
    CHECK(run_until_settled(400) > 0 && f3_mismatches(1, 2) == 0);
    for (int i = 0; i < 3; i++) fx_input(0, MI_LATCH_CLICK);
    CHECK(fx_pattern() == FX_MONO_FIRST + 0);   /* wraps after inverted, full rows */
    CHECK(fx_input(-1, MI_LATCH_NONE) == FX_NONE && fx_cursor() == 1);
    while (fx_cursor() != FX_ROW_F2) fx_input(1, MI_LATCH_NONE);
    CHECK(fx_input(0, MI_LATCH_CLICK) == FX_NONE && fx_screen() == FX_SCREEN_F2);
    CHECK(run_until_settled(400) > 0 && f2_mismatches() == 0);
    fx_other_layout();
    CHECK(fx_screen() == FX_SCREEN_F1 && fx_pattern() == 0);
    fx_set_mono(3);
    CHECK(!fx_set_pattern(0) && fx_screen() == FX_SCREEN_F3);   /* A and B are F1's */
    while (fx_cursor() != FX_ROW_DIAG) fx_input(1, MI_LATCH_NONE);
    CHECK(fx_input(0, MI_LATCH_CLICK) == FX_DIAG);
    fx_return_from_diag();
    CHECK(fx_screen() == FX_SCREEN_F1 && run_until_settled(400) > 0 && f1_mismatches(fx_pattern(), FX_ROW_DIAG) == 0);
    CHECK(fx_set_pattern(0));

    /* menu_text.c's edges and padding, on their own: a short string pads
     * with spaces; ink edges are set on every row asked for. */
    uint8_t   b[2 * 16];
    mt_line_t l = {"A", 3, 2, 3, true, false};
    CHECK(mt_width(&l) == 2 + 18 + 3);
    mt_bits(&l, 0, 23, 3, 2, b, 16);
    for (int r = 0; r < 2; r++) {
        CHECK((b[r * 16] & 0xC0) == 0xC0);       /* the lead, ink */
        CHECK((b[r * 16 + 2] & 0x0E) == 0);      /* the trail, background: columns 20-22 */
    }
    CHECK(((b[0] >> 5) & 1) == ((font_small_mono['A' - 0x20][3] >> 7) & 1));   /* 'A' column 0, row 3 */
    l.trail_ink = true;
    mt_bits(&l, 20, 3, 0, 1, b, 16);
    CHECK((b[0] & 0xE0) == 0xE0);   /* the trail, ink */
    l.s = "\x7f";
    mt_bits(&l, 2, 6, 0, MT_CELL_H, b, 1);
    for (int r = 0; r < MT_CELL_H; r++) CHECK(b[r] == (uint8_t)(font_small_mono['?' - 0x20][r] & 0xFC));   /* no glyph: '?' */
}

static void test_op_end(void) {
    /* The race revision 9 closes: navigation in the same pass an op reaches
     * the stop. The stop must already be latched, not cancelled. Each n,
     * glyph ops (a DMA) and fill ops (synchronous) alike. */
    for (uint8_t n = 1; n < FX_F1_OPS; n++) {
        settled_a();
        fx_set_pattern(1);
        ms_stop_after(n);
        int guard = 0;
        while (guard++ < 400) {
            pass();
            if (ms_stopped() || ms_ops() >= n) break;
        }
        fx_input(1, MI_LATCH_NONE);   /* navigation before the next pass */
        CHECK(ms_stopped());
        CHECK(!ms_stop_cancelled_take());
        CHECK(ms_ops() == 0);         /* the new target's count, the stop held */
        CHECK(pass() == MS_STEP_STOPPED);
    }

    /* A stop not yet reached is superseded by a retarget. */
    settled_a();
    fx_set_pattern(1);
    ms_stop_after(20);
    pass(); pass();
    fx_input(1, MI_LATCH_NONE);
    CHECK(!ms_stopped() && ms_stop_cancelled_take());

    /* A reached stop holds a newly requested clear paused, then lets it run. */
    settled_a();
    fx_set_pattern(1);
    ms_stop_after(5);
    int guard = 0;
    while (!ms_stopped() && guard++ < 400) pass();
    CHECK(ms_stopped());
    fx_other_layout();
    CHECK(ms_clearing() && pass() == MS_STEP_STOPPED && ms_clearing());
    ms_stop_release();
    CHECK(run_until_settled(400) > 0 && f2_mismatches() == 0);

    /* A loss in the pass an op reaches its stop: still latched. */
    settled_a();
    fx_set_pattern(1);
    ms_stop_after(12);
    guard = 0;
    while (guard++ < 400) {
        pass();
        if (ms_stopped() || ms_ops() >= 12) break;
    }
    fx_invalidate();
    CHECK(ms_stopped() && pass() == MS_STEP_STOPPED);

    /* Every failed piece ends its op at once: counted, a stop on it latched,
     * and the latch surviving navigation before the next pass. */
    settled_a();
    fx_set_pattern(1);
    int fullb = run_until_settled(400);
    int failed_pieces = 0;
    for (int k = 0; k < fullb; k++) {
        settled_a();
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        uint8_t o = ms_ops();
        ms_stop_after((uint8_t)(o + 1));
        fault_next_fill = 1;
        pass();
        if (fault_next_fill) { fault_next_fill = 0; continue; }   /* that pass wasn't a fill */
        failed_pieces++;
        CHECK(ms_ops() == o + 1 && ms_stopped());
        fx_input(1, MI_LATCH_NONE);
        CHECK(ms_stopped() && !ms_stop_cancelled_take());
    }
    CHECK(failed_pieces >= 4 * 2 * FX_ROWS);   /* every row piece at least */

    /* A glyph's DMA ends, then navigation or a loss comes before any
     * ms_step() or ms_ops(): new_target() and the invalidation settle it
     * first, so its stop is latched, not cancelled. */
    for (uint8_t n = 1; n <= 9; n++)
        for (int inval = 0; inval < 2; inval++) {
            settled_a();
            int g0 = glyph_ops;                           /* settled_a painted A's title */
            fx_set_pattern(1);
            ms_stop_after(n);
            int g = 0;
            while (g++ < 400) {
                pass();
                if (mb_busy() && glyph_ops - g0 >= n) break;   /* op n's DMA armed */
            }
            CHECK(mb_busy());
            dma_settle();                                 /* it completes */
            if (inval) fx_invalidate();
            else       fx_input(1, MI_LATCH_NONE);
            CHECK(ms_stopped());
            CHECK(!ms_stop_cancelled_take());
        }

    /* A reached stop is let go by a fresh opening, and by a return. */
    for (int ret = 0; ret < 2; ret++) {
        settled_a();
        fx_set_pattern(1);
        ms_stop_after(10);
        guard = 0;
        while (!ms_stopped() && guard++ < 400) pass();
        CHECK(ms_stopped());
        if (ret) fx_return_from_diag();
        else     fx_open();
        CHECK(!ms_stopped());
        CHECK(run_until_settled(400) > 0);
    }

    /* The final piece failing: its op still ends once, and the loss repaints. */
    settled_a();
    fx_set_pattern(1);
    ms_stop_after(11);   /* op 11: row 0's first half (glyphs 1-9, the separator, then this) */
    guard = 0;
    while (guard++ < 400 && ms_ops() < 10) pass();
    int f0 = fill_ops;
    guard = 0;
    while (guard++ < 50 && fill_ops < f0 + 3) pass();   /* three of its four pieces (a commit takes a pass too) */
    CHECK(fill_ops == f0 + 3 && ms_ops() == 10);
    fault_next_fill = 1;      /* the fourth gives up */
    guard = 0;
    while (guard++ < 50 && fault_next_fill) pass();
    CHECK(ms_stopped() && ms_ops() == 11);
    ms_stop_release();
    CHECK(run_until_settled(800) > 0 && f1_mismatches(1, 0) == 0);
}

/* --- C10: the scheduler's measures ------------------------------------------------ */

static void test_meas(void) {
    settled_a();
    uint8_t g0 = ms_tgen(), s0 = ms_settled_count(), x0 = ms_superseded_count();
    /* A target that settles: settled +1, nothing superseded. */
    fx_set_pattern(1);
    CHECK(run_until_settled(400) > 0);
    CHECK((uint8_t)(ms_tgen() - g0) == 1 && (uint8_t)(ms_settled_count() - s0) == 1);
    CHECK(ms_superseded_count() == x0);
    /* A loss's repaint of the same target doesn't settle it again. */
    fault_next_dma = 1;
    fx_set_pattern(0);
    CHECK(run_until_settled(800) > 0);
    CHECK((uint8_t)(ms_settled_count() - s0) == 2);
    /* Targets replaced before they settle are superseded, and the books
     * balance: created = settled + superseded + at most the one outstanding. */
    g0 = ms_tgen(); s0 = ms_settled_count(); x0 = ms_superseded_count();
    for (int i = 0; i < 10; i++) {
        fx_input(1, MI_LATCH_NONE);
        pass(); pass();
    }
    uint8_t created = (uint8_t)(ms_tgen() - g0);
    uint8_t books   = (uint8_t)((ms_settled_count() - s0) + (ms_superseded_count() - x0));
    CHECK(created == 10 && (created == books || created == books + 1));
    CHECK(run_until_settled(400) > 0);
    CHECK((uint8_t)((ms_settled_count() - s0) + (ms_superseded_count() - x0)) == 10);
    /* Op latency, piece cost, repaint latency: measured and ordered. A fill
     * op's four pieces take four passes (4,000 + 4 x 300 ticks of the fake). */
    ms_meas_reset();
    fx_set_pattern(1);
    CHECK(run_until_settled(400) > 0);
    CHECK(ms_piece_max_ticks() >= 300 && ms_op_max_ticks() >= ms_piece_max_ticks());
    CHECK(ms_repaint_max_ticks() >= ms_op_max_ticks() && ms_last_op_ticks() > 0);
    /* An op abandoned by a retarget isn't timed: the last ended op's latency
     * stays what it was. */
    uint32_t last = ms_last_op_ticks();
    fx_set_pattern(0);
    pass();                       /* row 0's first piece starts an op */
    fx_input(1, MI_LATCH_NONE);   /* ...abandoned */
    CHECK(ms_last_op_ticks() == last);

    /* A glyph op's latency ends at its DMA's end, however late it's noticed. */
    settled_a();
    fx_set_pattern(1);
    int g = 0;
    while (g++ < 50 && !mb_busy()) pass();   /* the title's first glyph armed */
    CHECK(mb_busy());
    uint32_t t_arm = fake_ticks;
    fake_ticks += 100;
    dma_settle();                 /* it ends 100 ticks after its arm */
    fake_ticks += 50000;          /* ...and nothing looks for 50,000 */
    (void)ms_ops();
    CHECK(ms_last_op_ticks() <= 100 + (fake_ticks - 50000 - t_arm) && ms_last_op_ticks() < 50000);

    /* A retarget to the target already painted settles at once: the same
     * pattern again, then another, with no pass or read between. */
    settled_a();
    uint8_t s1 = ms_settled_count(), x1 = ms_superseded_count();
    fx_set_pattern(0);            /* A again: already on the panel */
    fx_set_pattern(1);            /* B before any pass */
    CHECK((uint8_t)(ms_settled_count() - s1) == 1 && ms_superseded_count() == x1);

    /* A knob spin: a detent every 4 passes, half a row's 8 pieces. Slots the
     * cursor has left keep their signature, so they resume and commit; under
     * the old generation rule every detent restarted them and nothing did. */
    settled_a();
    int commits_in_burst = 0;
    for (int b = 0; b < 25; b++) {
        uint8_t c0 = ms_committed_count();
        fx_input(1, MI_LATCH_NONE);
        for (int i = 0; i < 4; i++) pass();
        commits_in_burst += (uint8_t)(ms_committed_count() - c0);
    }
    CHECK(commits_in_burst >= 4);   /* C10 asks one a 500 ms, ~50 passes: twice that, at least */
    CHECK(run_until_settled(400) > 0 && f1_mismatches(0, (uint8_t)(25 % FX_ROWS)) == 0);

    /* An op cut by a retarget that leaves its slot's signature alone resumes,
     * and counts when it ends -- untimed: its latency isn't the resumed
     * suffix's. At every pass of a B repaint, a selection change there and
     * back (no slot's signature changes); the first op to end afterwards is
     * either untimed (last unchanged) or a whole op begun after the
     * retarget. A fill op is four pieces: 3 x 1,000 + 4 x 300 ticks. */
    settled_a();
    fx_set_pattern(1);
    int fullb2 = run_until_settled(400);
    int checked = 0;
    for (int k = 1; k < fullb2; k++) {
        settled_a();
        fx_set_pattern(1);
        for (int i = 0; i < k; i++) pass();
        /* Within the rows' ops (11-26): past the title's glyphs and the
         * separator, and before the one-piece scrollbar, which a retarget at
         * its boundary times whole and short. */
        if (ms_ops() < 10 || ms_ops() >= 10 + 2 * FX_ROWS) continue;
        uint32_t last0 = ms_last_op_ticks();
        int      f0    = fill_ops;
        fx_input(1, MI_LATCH_NONE);
        fx_input(-1, MI_LATCH_NONE);
        int g = 0;
        while (g++ < 50 && ms_ops() == 0) pass();
        CHECK(ms_ops() == 1);
        uint32_t last1 = ms_last_op_ticks();
        CHECK(last1 == last0 || last1 >= 3u * 1000u + 4u * 300u);
        if (fill_ops - f0 < 4) checked++;     /* a resumed op: fewer than its four pieces after */
    }
    CHECK(checked >= 3 * FX_ROWS);

    /* A retarget while a glyph flies: its end is still counted, in the new
     * target, once. */
    settled_a();
    fx_set_pattern(1);
    int g2 = 0;
    while (g2++ < 50 && !mb_busy()) pass();
    CHECK(mb_busy());
    fx_input(1, MI_LATCH_NONE);   /* the title's signature unchanged */
    CHECK(ms_ops() == 0);
    dma_settle();
    CHECK(ms_ops() == 1);
    CHECK(ms_ops() == 1);         /* once */
}

/* --- menu_ops.c through a fake environment -------------------------------------
 * The production task, op 27 and menu-side actions, with menu_env.h faked:
 * env_po_event runs po_event and then applies its actions as display.c's
 * po_apply does -- the display's own (buffers, overlays) are no-ops here, the
 * menu's side is the production menu_ops_apply(). */
static uint32_t fk_now;
static bool     fk_wake_notice, fk_wake_held;

uint16_t env_po_event(po_event_t ev) {
    uint16_t a = po_event(ev, fk_wake_held, fk_now);
    if (a & PO_ACT_REFUSED) return a;
    bool dropped = false;
    if (a & PO_ACT_QUIESCE_DROP) {
        dma_settle();
        dropped = take_lost();
    }
    menu_ops_apply(a, dropped, fk_now);
    return a;
}
void    env_lost_inject(void) { lost_latched = true; }
bool    env_wake_notice_take(void) { bool n = fk_wake_notice; fk_wake_notice = false; return n; }
bool    env_wake_held(void) { return fk_wake_held; }
bool    env_batt_dirty(void) { return false; }
bool    env_logo_stale(void) { return false; }
uint8_t env_queue_depths(void) { return 0; }
bool    env_probe_handoff(uint8_t *out4) { (void)out4; return false; }   /* display.c's: the board's A3 */
static uint16_t fk_token;
static uint8_t  fk_health_gen;
void env_meas(env_meas_t *m) {
    memset(m, 0, sizeof *m);
    m->token      = fk_token;
    m->health_gen = fk_health_gen;
    m->dbg_sec    = 0xFFu;
    m->rtc_sec    = 0xFFu;
}
uint16_t env_meas_arm(void) {
    if (++fk_token == 0) fk_token = 1;
    return fk_token;
}
bool env_debug_done(void) { return false; }

/* One main-loop pass as housekeeping_task_kb runs it: the task, then the pump
 * (its loss taken at the top, then the owner's operation). */
static void fw_pass(uint32_t dt) {
    fk_now += dt;
    fake_ticks += dt * (MB_TICK_HZ / 1000u);
    menu_ops_task(fk_now);
    dma_settle();
    if (take_lost()) {
        uint16_t a = po_loss(fk_now);
        menu_note_loss();
        if (a & PO_ACT_RESET_BUFFERS) menu_screen_invalidate();
    }
    if (po_owner() == PANEL_MENU) menu_pump();
}

static uint8_t rpt[32];
static uint8_t op27(uint8_t sub, int a0, int a1) {
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = sub;
    rpt[5] = (uint8_t)a0; rpt[6] = (uint8_t)a1;
    if (!menu_ops_op27(rpt, fk_now)) return 0xFF;
    return rpt[5];   /* the status; rpt[6] the seq */
}
static mi_state_t wait_terminal(uint8_t seq, int max_passes) {
    for (int i = 0; i < max_passes; i++) {
        if (mi_last_seq() == seq && mi_last_state() != MI_ST_PENDING) return mi_last_state();
        fw_pass(5);
    }
    return MI_ST_PENDING;
}
static void fw_reset(void) {
    fake_reset();
    po_init();
    mi_init();
    ms_init();
    fk_now = 1000;
    fk_wake_notice = fk_wake_held = false;
    po_event(PO_EV_STARTUP, false, 0);
    while (po_phase() != RESTORE_RESIDUAL) po_restore_advance();
    po_residual_in_t in = {0};
    po_residual_next(&in, 0);
}
static void open_fixture(void) {
    CHECK(op27(4, 0, 0) == MI_OK && mi_last_state() == MI_ST_DONE);
    CHECK(po_owner() == PANEL_MENU && fx_screen() == FX_SCREEN_F1);
    for (int i = 0; i < 300 && !(ms_settled() && !mb_busy()); i++) fw_pass(5);
    CHECK(ms_settled());
}

static void test_ops(void) {
    uint8_t seq;

    /* Framing and validation: an unknown sub is unhandled; the states a sub
     * can't take answer 2 and leave nothing outstanding. */
    fw_reset();
    CHECK(op27(31, 0, 0) == 0xFF);   /* C10 moved A1's unknown sub from 10 to 31 */
    /* Sub 10 (C10): read at once, arm 1 issues a new token, a bad arm 2. */
    CHECK(op27(10, 2, 0) == MI_BAD);
    CHECK(op27(10, 0, 0) == MI_OK && (rpt[26] | rpt[27] << 8) == 0);   /* no session yet */
    CHECK(op27(10, 1, 0) == MI_OK);
    CHECK(op27(10, 0, 0) == MI_OK && (rpt[26] | rpt[27] << 8) == 1);
    CHECK(rpt[30] == 0xFF && rpt[29] == 0xFF);   /* the fake has no RTC and no debug page */
    CHECK(op27(9, 0, 0) == MI_OK && mi_last_state() == MI_ST_REFUSED);   /* the probe is display.c's: the board's A3 */
    CHECK(op27(1, 1, 0) == MI_BAD && mi_outstanding() == MI_KIND_NONE);   /* no session */
    CHECK(op27(0, 0, 0) == MI_BAD);
    CHECK(op27(6, 2, 0) == MI_BAD);
    CHECK(op27(5, 0, 0) == MI_OK && rpt[8] == PANEL_DASH && rpt[9] == SESSION_NONE && rpt[12] == RESTORE_DONE);
    open_fixture();
    CHECK(op27(1, 0, 0) == MI_BAD && op27(1, 17, 0) == MI_BAD && op27(1, (uint8_t)-17, 0) == MI_BAD);
    CHECK(op27(3, 10, 0) == MI_BAD && op27(3, 0x89, 0x13) == MI_BAD);   /* 49 ms, 5001 ms */
    CHECK(op27(0, 0, 3) == MI_BAD && op27(0, 4, 0) == MI_BAD && op27(0, 2, 0) == MI_BAD && op27(0, 2, 27) == MI_BAD);

    /* Single flight: a second mutation is busy and leaves the first alone. */
    CHECK(op27(2, 0, 0) == MI_OK);
    seq = rpt[6];
    CHECK(op27(1, 1, 0) == MI_BUSY && rpt[6] == 0 && mi_last_seq() == seq);
    CHECK(wait_terminal(seq, 5) == MI_ST_DONE);
    CHECK(fx_pattern() == 1);   /* row 0's click toggled */

    /* Finding 1: synthetic +1 cancelled to a net zero by a physical -1 still ends. */
    CHECK(op27(1, 1, 0) == MI_OK);
    seq = rpt[6];
    CHECK(menu_physical(MI_CCW, true, false, fk_now) == false);
    CHECK(menu_physical(MI_CCW, false, false, fk_now) == false);
    CHECK(wait_terminal(seq, 3) == MI_ST_DONE && fx_cursor() == 0);
    /* ... and a synthetic click discarded by a physical close is superseded. */
    CHECK(op27(2, 0, 0) == MI_OK);
    seq = rpt[6];
    menu_physical(MI_KNOB, true, true, fk_now);    /* Fn plus a click: close */
    CHECK(wait_terminal(seq, 3) == MI_ST_SUPERSEDED);
    CHECK(po_session() == SESSION_NONE);
    menu_physical(MI_KNOB, false, false, fk_now);
    CHECK(mi_capture_bits() == 0);

    /* The hold, through the production task: Back at 600 ms closes the
     * fixture, and the close cancels the hold before its 650 ms release. */
    open_fixture();
    CHECK(op27(3, 0, 0) == MI_OK);
    seq = rpt[6];
    CHECK(wait_terminal(seq, 200) == MI_ST_CANCELLED && po_session() == SESSION_NONE);
    /* A 300 ms hold is a click, done after its release. */
    open_fixture();
    CHECK(op27(3, 0x2C, 0x01) == MI_OK);
    seq = rpt[6];
    CHECK(wait_terminal(seq, 200) == MI_ST_DONE && po_session() == SESSION_OPEN && fx_pattern() == 1);

    /* Finding 2: a pending stop disposed of by physical navigation ends
     * superseded; a reached stop holds through navigation until the next sub 0. */
    CHECK(op27(0, 0, 0) == MI_OK);
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    CHECK(op27(0, 2, 20) == MI_OK);
    seq = rpt[6];
    fw_pass(5);
    menu_physical(MI_CW, true, false, fk_now);
    menu_physical(MI_CW, false, false, fk_now);
    CHECK(wait_terminal(seq, 10) == MI_ST_SUPERSEDED && !ms_stopped());
    CHECK(op27(0, 0, 0) == MI_OK);
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    CHECK(op27(0, 2, 5) == MI_OK);
    seq = rpt[6];
    CHECK(wait_terminal(seq, 100) == MI_ST_DONE && ms_stopped() && ms_ops() == 5);
    menu_physical(MI_CW, true, false, fk_now);
    menu_physical(MI_CW, false, false, fk_now);
    for (int i = 0; i < 10; i++) fw_pass(5);
    CHECK(ms_stopped());                       /* held through turns */
    /* ... and through a layout-changing click: no clear runs while held. */
    for (int g = 0; g < 16 && fx_cursor() != FX_ROW_F2; g++) {
        menu_physical(MI_CW, true, false, fk_now);
        menu_physical(MI_CW, false, false, fk_now);
        fw_pass(5);
    }
    if (fx_cursor() != FX_ROW_F2) printf("cursor %u session %u owner %u\n", fx_cursor(), po_session(), po_owner());
    CHECK(fx_cursor() == FX_ROW_F2);
    int b0 = bands_ok;
    menu_physical(MI_KNOB, true, false, fk_now);
    fk_now += 50;
    menu_physical(MI_KNOB, false, false, fk_now);
    for (int i = 0; i < 20; i++) fw_pass(5);
    CHECK(fx_screen() == FX_SCREEN_F2 && ms_stopped() && bands_ok == b0 && ms_clearing());
    CHECK(op27(0, 3, 0) == MI_OK && !ms_stopped());   /* sub 0 lets go: back to F1, the clear finishes */
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    CHECK(ms_settled() && fx_screen() == FX_SCREEN_F1);
    CHECK(op27(0, 0, 0) == MI_OK && !ms_stopped());
    CHECK(op27(5, 0, 0) == MI_OK && rpt[30] == 0);

    /* Finding 8: an armed glyph isn't a completed operation until it ends. */
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    fx_set_pattern(1);
    for (int g = 0; g < 50 && !mb_busy(); g++) CHECK(ms_step() != MS_STEP_IDLE);   /* the title's first glyph arms */
    CHECK(mb_busy());
    CHECK(ms_ops() == 0);
    dma_settle();
    CHECK(ms_ops() == 1);

    /* Finding 7: navigation during a layout's clear doesn't restart it. */
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    bands_ok = 0;
    fx_other_layout();          /* F1 to F2 */
    pass(); pass();
    CHECK(bands_ok == 2 && ms_clearing());
    fx_other_layout();          /* back to F1 mid-clear */
    for (int i = 0; i < 300 && ms_clearing(); i++) pass();
    CHECK(bands_ok == MB_BANDS);   /* 8 bands in all, not 2 + 8 */

    /* Sub 7 under MENU: installed as WAITING, done at once. */
    CHECK(op27(7, 0, 0) == MI_OK && mi_last_state() == MI_ST_DONE && po_phase() == RESTORE_WAITING);
    /* Sub 8, taken by the MENU handler: done, counted, everything repainted. */
    for (int i = 0; i < 300 && !ms_settled(); i++) fw_pass(5);
    CHECK(op27(8, 0, 0) == MI_OK);
    seq = rpt[6];
    CHECK(wait_terminal(seq, 3) == MI_ST_DONE && ms_unsettled() > 0);
    CHECK(op27(5, 0, 0) == MI_OK && rpt[22] == 1);
    /* Sub 8 dropped at an ownership change: superseded. */
    CHECK(op27(8, 0, 0) == MI_OK);
    seq = rpt[6];
    env_po_event(PO_EV_DIAG_HEALTH);   /* the click to Diagnostics, before the pump took it */
    CHECK(mi_last_seq() == seq && mi_last_state() == MI_ST_SUPERSEDED && !mb_lost_pending());
    CHECK(po_owner() == PANEL_DEBUG);
    fw_pass(5);
    /* A click under DEBUG returns to the fixture at Diagnostics' row. */
    CHECK(op27(2, 0, 0) == MI_OK);
    seq = rpt[6];
    CHECK(wait_terminal(seq, 3) == MI_ST_DONE && po_owner() == PANEL_MENU && fx_cursor() == FX_ROW_DIAG);

    /* Disarming closes a session; arming lets the physical opener in. */
    CHECK(op27(6, 1, 0) == MI_OK && menu_enabled());
    CHECK(op27(6, 0, 0) == MI_OK && po_session() == SESSION_NONE && !menu_enabled());
    CHECK(menu_physical(MI_KNOB, true, true, fk_now) == true);    /* not armed: forwarded */
    CHECK(menu_physical(MI_KNOB, false, true, fk_now) == true);
    op27(6, 1, 0);
    CHECK(menu_physical(MI_KNOB, true, true, fk_now) == false && po_session() == SESSION_OPEN);
    op27(6, 0, 0);   /* disarm while open: closed, the release still owed */
    CHECK(po_session() == SESSION_NONE && mi_capture_bits() == 1u);
    CHECK(menu_physical(MI_KNOB, false, false, fk_now) == false && mi_capture_bits() == 0);

    /* The pending opening: under the wake hold, then opened by the notice. */
    op27(6, 1, 0);
    fk_wake_held = true;
    CHECK(menu_physical(MI_KNOB, true, true, fk_now) == false && po_session() == SESSION_PENDING);
    menu_physical(MI_KNOB, false, false, fk_now);
    fk_wake_held = false;
    fk_wake_notice = true;
    fw_pass(5);
    CHECK(po_session() == SESSION_OPEN && po_owner() == PANEL_MENU);

    /* The 24 s idle timeout, from the last knob input. */
    fw_pass(MI_IDLE_MS - 10);
    CHECK(po_session() == SESSION_OPEN);
    fw_pass(20);
    CHECK(po_session() == SESSION_NONE);
    CHECK(po_invariant_fail() == 0);
}

/* The expected frames for the board's photographs (CONFIG-MENU-S0-BOARD-TESTS
 * A13): the fixture's A, B stopped after n operations, and F2, as PPM images
 * drawn by the production slots and fixture on the fake panel. A glyph's cell
 * is drawn light grey: the photo has the real glyph there. */
static void write_ppm(const char *dir, const char *name) {
    char path[512];
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *f = fopen(path, "wb");
    if (!f) { printf("can't write %s\n", path); fails++; return; }
    fprintf(f, "P6\n%d %d\n255\n", MB_W, MB_H);
    for (int y = 0; y < MB_H; y++)
        for (int x = 0; x < MB_W; x++) {
            uint16_t c = fb[y][x];
            unsigned char px[3];
            if (is_glyph[y][x]) { px[0] = px[1] = px[2] = 220; }   /* a glyph's cell */
            else {
                px[0] = (unsigned char)(((c >> 11) & 31) * 255 / 31);
                px[1] = (unsigned char)(((c >> 5) & 63) * 255 / 63);
                px[2] = (unsigned char)((c & 31) * 255 / 31);
            }
            fwrite(px, 1, 3, f);
        }
    fclose(f);
    printf("wrote %s\n", path);
}

static int frames(const char *dir, int n) {
    fake_reset();
    ms_init();
    fx_open();
    run_until_settled(300);
    write_ppm(dir, "fixture-A.ppm");
    fx_set_pattern(1);
    ms_stop_after((uint8_t)n);
    for (int i = 0; i < 300 && !ms_stopped(); i++) pass();
    char name[32];
    snprintf(name, sizeof name, "fixture-B-stop%d.ppm", n);
    write_ppm(dir, name);
    ms_stop_release();
    fx_set_pattern(0);
    run_until_settled(300);
    write_ppm(dir, "fixture-A-again.ppm");
    fx_other_layout();
    run_until_settled(300);
    write_ppm(dir, "fixture-F2.ppm");
    /* 0x8010, a fixture colour that equals a glyph code, stays purple: F2's
     * tile 7 and A's fourth row (codex's third verification). */
    CHECK(!is_glyph[7 / 4 * 32 + 16][7 % 4 * 32 + 16] && fb[7 / 4 * 32 + 16][7 % 4 * 32 + 16] == 0x8010);
    /* S1's F3, each style, the cursor on row 2. */
    for (uint8_t st = 0; st < FX_MONO_STYLES; st++) {
        fx_set_mono(st);
        while (fx_cursor() != 2) fx_input(1, MI_LATCH_NONE);
        run_until_settled(400);
        snprintf(name, sizeof name, "fixture-F3-%u.ppm", st);
        write_ppm(dir, name);
    }
    return fails ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc >= 3 && strcmp(argv[1], "frames") == 0)
        return frames(argv[2], argc >= 4 ? atoi(argv[3]) : 13);
    test_transitions();
    test_restore_residual_and_loss();
    test_input();
    test_op27_flight();
    test_fixture_paint();
    test_pieces();
    test_mono();
    test_op_end();
    test_meas();
    test_ops();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("menu S0: all checks passed\n");
    return 0;
}
