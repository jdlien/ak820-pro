/* Host test of the configuration menu's S0 foundations: the owner, session and
 * restore (menu/panel_owner.c), the knob's capture and op 27's single flight
 * (menu/menu_input.c), the damage model (menu/menu_slots.c), the fixture
 * (menu/menu_fixture.c), and the task, op 27 and the menu's side of an owner
 * event (menu/menu_ops.c), against a fake framebuffer and environment, and S1's
 * mono text (menu/menu_text.c, the fixture's F3). These are the firmware's
 * own files: plans/CONFIG-MENU-BUILD-PLAN.md, "S0" and "S1". Build and run:
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -DMENU_HOST_TEST -I $D/menu scripts/menu_s0_test.c \
 *       $D/menu/panel_owner.c $D/menu/menu_input.c $D/menu/menu_slots.c \
 *       $D/menu/menu_fixture.c $D/menu/menu_ops.c $D/menu/menu_text.c $D/menu/menu.c \
 *       $D/menu/menu_edit.c -o ms0 && ./ms0
 *
 * and again with -DMENU_ENABLE (the production opener, P1a): that build runs
 * test_menu_enable() only, since the S0 suite expects the opener off unarmed.
 *
 * The fake mb_mono stands in for lcd_blit_mono: the stream's byte order, CS
 * and scratch handling and its failure paths are the board's tests
 * (scripts/menu_s1_fault.py), not these.
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
#include "menu.h"
#include "menu_edit.h"
#include "../graphics/res/font_small_mono.h"   /* through -I $D/menu */
#include "../indicator_levels.h"               /* P2a: the indicators' levels and tick */

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
static uint16_t dma_x, dma_y, dma_col, dma_w = MB_GLYPH_W, dma_h = MB_GLYPH_H;
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
    paint_fb(dma_x, dma_y, (uint16_t)(dma_x + dma_w - 1), (uint16_t)(dma_y + dma_h - 1), dma_col, true);
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
    dma_w = MB_GLYPH_W; dma_h = MB_GLYPH_H;
    glyph_ops++;
    return true;
}
/* P1b: a big glyph (FONT_STATUS) is a DMA as a small one is; its cell is
 * painted as big_color(c). */
static uint16_t big_color(char c) { return (uint16_t)(0xB000u | (uint8_t)c); }
static int      big_ops;
bool mb_glyph_big(char c, uint16_t x, uint16_t y) {
    if (bus_busy_once) { bus_busy_once = false; return false; }
    if (dma_busy) return false;
    dma_busy = true;
    dma_x = x; dma_y = y; dma_col = big_color(c);
    dma_w = MB_BIG_W; dma_h = MB_BIG_H;
    big_ops++;
    return true;
}
/* P1b: generated rows, a polled stream as mb_mono's (its faults too); the
 * rows come in panel order, the frame keeps RGB565. */
static int pixel_ops;
bool mb_rows(uint16_t x, uint16_t y, uint16_t w, uint16_t h, mb_row_fn fn, const void *ctx) {
    dma_settle();
    pass_bytes += (uint32_t)w * h * 2u;
    uint16_t rows = h;
    bool     ok   = true;
    if (fault_next_fill > 0) {
        fault_next_fill--;
        rows = fault_fill_prefix ? (uint16_t)(h / 2u) : 0;
        lost_latched = true;
        ok           = false;
    }
    for (uint16_t r = 0; r < rows; r++) {
        uint16_t px[MB_W];
        fn(ctx, r, px, w);
        for (uint16_t c = 0; c < w; c++) {
            fb[y + r][x + c]       = MB_PANEL(px[c]);
            is_glyph[y + r][x + c] = false;
        }
    }
    if (ok) pixel_ops++;
    fake_ticks += 300;
    return ok;
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
        int full = run_until_settled(400);   /* st's repaint, which the selection change interrupts */
        fx_set_mono((uint8_t)(st + 1));
        int next = run_until_settled(400);   /* st + 1's, which the style change and the faults interrupt */
        fx_set_mono(st);
        CHECK(full > 0 && next > 0 && run_until_settled(400) > 0);
        int consumed = 0, most = full > next ? full : next;
        for (int k = 0; k < most; k++) {
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
        CHECK(consumed >= next);
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

    /* mt_bits against a per-pixel reference over every band start and width
     * up to 128, every cell count 0-20, leads and trails 0-2 and both inks,
     * short strings, the extras and a code the face hasn't, glyph rows 0-13.
     * Bits past w must stay clear, and the bytes after the band untouched.
     * Then codex's wrap case: a 255-cell line, where the one-past cell index
     * is 256. */
    {
        static const char *const ss[] = {"", "A", "Hi, gjpqy|", "\x80\x81\x82\x83\x84\x7f~", "WWWWWWWWWWWWWWWWWWWW"};
        uint8_t bb[14 * 17];
        int     bad = 0, cases = 0;
        for (unsigned si = 0; si < sizeof ss / sizeof ss[0]; si++)
            for (uint8_t cells = 0; cells <= 20; cells++)
                for (uint8_t lead = 0; lead <= 2; lead++)
                    for (uint8_t trail = 0; trail <= 2; trail++)
                        for (int inks = 0; inks < 4; inks++) {
                            mt_line_t ln = {ss[si], cells, lead, trail, (inks & 1) != 0, (inks & 2) != 0, 0};
                            uint16_t  lw = mt_width(&ln);
                            size_t    sl = strlen(ss[si]);
                            for (uint16_t c0 = 0; c0 < lw; c0++)
                                for (uint16_t w = 1; c0 + w <= lw && w <= 128; w++) {
                                    uint8_t st = (uint8_t)((w + 7) / 8 + (w % 3 == 0));   /* sometimes a spare byte */
                                    uint8_t r0 = (uint8_t)((c0 + w) % 14), rows = (uint8_t)(1 + (w % 3));
                                    if (r0 + rows > 14) r0 = (uint8_t)(14 - rows);
                                    memset(bb, 0xA5, sizeof bb);
                                    mt_bits(&ln, c0, w, r0, rows, bb, st);
                                    cases++;
                                    for (uint8_t r = 0; r < rows; r++)
                                        for (uint16_t i = 0; i < st * 8u; i++) {
                                            uint16_t c   = (uint16_t)(c0 + i);
                                            bool     got = (bb[r * st + i / 8] >> (7 - i % 8)) & 1, want = false;
                                            if (i < w) {
                                                if (c < lead) want = ln.lead_ink;
                                                else if (c >= lead + cells * 6) want = ln.trail_ink;
                                                else {
                                                    size_t  cell = (size_t)(c - lead) / 6;
                                                    uint8_t code = cell < sl ? (uint8_t)ss[si][cell] : (uint8_t)' ';
                                                    const uint8_t *g = code >= 0x20 && code < 0x7f ? font_small_mono[code - 0x20]
                                                                     : code >= 0x80 && code < 0x80 + FONT_MONO_N - 95 ? font_small_mono[95 + code - 0x80]
                                                                     : font_small_mono['?' - 0x20];
                                                    want = (g[r0 + r] >> (7 - (c - lead) % 6)) & 1;
                                                }
                                            }
                                            if (got != want) bad++;
                                        }
                                    for (size_t k = (size_t)rows * st; k < sizeof bb; k++)
                                        if (bb[k] != 0xA5) { bad++; break; }   /* past the band: untouched */
                                }
                        }
        CHECK(bad == 0 && cases > 100000);
        if (bad) printf("mt_bits: %d wrong bits\n", bad);

        static char ws[256];
        memset(ws, 'W', 255);
        mt_line_t wide = {ws, 255, 0, 1, false, false, 0};
        memset(bb, 0xA5, sizeof bb);
        mt_bits(&wide, 1524, 7, 3, 1, bb, 1);   /* the last glyph's six columns and one trail pixel */
        CHECK(bb[0] == (uint8_t)(font_small_mono['W' - 0x20][3] & 0xFC) && bb[1] == 0xA5);
    }
    /* The completion predicate: a loss latched and not yet taken isn't
     * settled, though every slot is committed (codex, P1's design review). */
    settled_a();
    CHECK(ms_settled());
    lost_latched = true;
    CHECK(!ms_settled());
    CHECK(run_until_settled(400) > 0 && f1_mismatches(0, 0) == 0);   /* pass() takes it: a repaint */

    /* menu_text.c's edges and padding, on their own: a short string pads
     * with spaces; ink edges are set on every row asked for. */
    uint8_t   b[2 * 16];
    mt_line_t l = {"A", 3, 2, 3, true, false, 0};
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

    /* A lead glyph (the menu's cursor, JD 10-24): its columns fill the lead,
     * over lead_ink, cut to the band; the glyph never reaches column 3, the
     * 1 px gap before cell 0. */
    const uint8_t *cg = font_small_mono[95 + (uint8_t)MT_CURSOR[0] - 0x80];
    mt_line_t      lg = {"A", 1, 4, 1, true, false, (uint8_t)MT_CURSOR[0]};
    CHECK(cg[5] == 0x80 && cg[0] == 0x80 && cg[13] == 0);   /* the thin bar (JD, 10-24): column 0, rows 0-12 */
    mt_bits(&lg, 0, 11, 0, MT_CELL_H, b, 2);
    for (int r = 0; r < MT_CELL_H; r++) {
        CHECK((cg[r] & 0x1F) == 0);
        CHECK((b[r * 2] & 0xF0) == (cg[r] & 0xF0));
        CHECK(((b[r * 2] >> 3) & 1) == ((font_small_mono['A' - 0x20][r] >> 7) & 1));   /* 'A' column 0 at line column 4 */
    }
    mt_bits(&lg, 2, 3, 0, MT_CELL_H, b, 1);   /* a band from column 2: the glyph's column 2, the gap, 'A' */
    for (int r = 0; r < MT_CELL_H; r++)
        CHECK((b[r] & 0xE0) == (uint8_t)(((cg[r] << 2) & 0x80) | ((font_small_mono['A' - 0x20][r] >> 2) & 0x20)));

    /* menu_text.h spells the generator's codes. */
    CHECK(!strcmp(MT_LSAQUO, FONT_MONO_LSAQUO) && !strcmp(MT_RSAQUO, FONT_MONO_RSAQUO) &&
          !strcmp(MT_BULLET, FONT_MONO_BULLET) && !strcmp(MT_TRIANGLE, FONT_MONO_TRIANGLE) &&
          !strcmp(MT_CHECK, FONT_MONO_CHECK));
    CHECK(!strcmp(MT_TRI_L, FONT_MONO_TRI_L) && !strcmp(MT_TRI_R, FONT_MONO_TRI_R) &&
          !strcmp(MT_CURSOR, FONT_MONO_CURSOR) && !strcmp(MT_WRENCH, FONT_MONO_WRENCH) &&
          !strcmp(MT_CHECK_BOX, FONT_MONO_CHECK_BOX));
    CHECK(!strcmp(MT_I_POWER, FONT_MONO_I_POWER) && !strcmp(MT_I_CLOCK, FONT_MONO_I_CLOCK) &&
          !strcmp(MT_I_DIAG, FONT_MONO_I_DIAG) && !strcmp(MT_I_HELP, FONT_MONO_I_HELP) &&
          !strcmp(MT_I_ABOUT, FONT_MONO_I_ABOUT) && !strcmp(MT_I_EXIT, FONT_MONO_I_EXIT));
    CHECK(!strcmp(MT_I_LIGHT, FONT_MONO_I_LIGHT) && !strcmp(MT_I_SCREEN, FONT_MONO_I_SCREEN) &&
          !strcmp(MT_I_BOOT, FONT_MONO_I_BOOT));
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

/* P1a's settings and facts. */
static uint8_t fk_power = 1, fk_clock = 0;
static int     fk_power_writes, fk_clock_writes, fk_resets;
uint8_t env_power_mode(void) { return fk_power; }
void    env_power_set(uint8_t m) { fk_power = m; fk_power_writes++; }
uint8_t env_clock_mode(void) { return fk_clock; }
void    env_clock_set(uint8_t m) { fk_clock = m; fk_clock_writes++; }
void    env_health_reset(void) { fk_resets++; }
/* P4: the battery readout. */
static bool fk_batt_hours;
static int  fk_batt_writes;
bool env_batt_hours(void) { return fk_batt_hours; }
void env_batt_hours_set(bool h) { fk_batt_hours = h; fk_batt_writes++; }

/* P1b's primitives over a fake RGB core with QMK's semantics: the mode and
 * HSV setters do nothing while the lights are off; a saving setter raises
 * the dirty flag, a _noeeprom one leaves it; the flush (fk_flush) writes
 * the config to the fake EEPROM only when dirty and the board's hold allows
 * (menu_edit_rgb_open). The LCD: the requested level, and its saved copy. */
static env_rgb_t fk_rgb = {2, 240, 215, 86, 127, 1, 0xFF}, fk_rgb_ee;
static bool      fk_rgb_dirty;
static int       fk_rgb_noop;   /* setter calls QMK ignored (the lights off) */
static uint8_t   fk_lcd = 52, fk_lcd_saved = 52;   /* 0-100 since P2b */
static int       fk_lcd_saves;
void env_rgb_get(env_rgb_t *c) { *c = fk_rgb; }
void env_rgb_mode(uint8_t mode, bool save) {
    if (!fk_rgb.enable) { fk_rgb_noop++; return; }
    fk_rgb.mode = mode;
    if (save) fk_rgb_dirty = true;
}
void env_rgb_hsv(uint8_t h, uint8_t s, uint8_t v, bool save) {
    if (!fk_rgb.enable) { fk_rgb_noop++; return; }
    fk_rgb.h = h; fk_rgb.s = s; fk_rgb.v = v;
    if (save) fk_rgb_dirty = true;
}
void env_rgb_speed(uint8_t speed, bool save) {
    fk_rgb.speed = speed;
    if (save) fk_rgb_dirty = true;
}
void env_rgb_flags(uint8_t flags) { fk_rgb.flags = flags; }
void env_rgb_enable(bool on, bool save) {
    fk_rgb.enable = on ? 1u : 0u;
    if (save) fk_rgb_dirty = true;
}
static void fk_flush(void) {
    if (fk_rgb_dirty && !menu_edit_rgb_open()) {
        fk_rgb_ee    = fk_rgb;
        fk_rgb_dirty = false;
    }
}
uint8_t env_lcd_level(void) { return fk_lcd; }
void    env_lcd_set(uint8_t level, bool save) {
    fk_lcd = level;
    if (save) { fk_lcd_saved = level; fk_lcd_saves++; }
}
/* P2a's indicator groups: the live level, its saved copy, the force bits. */
static uint8_t fk_ind[2] = {1, 0}, fk_ind_saved[2] = {1, 0}, fk_ind_force;
static int     fk_ind_saves;
uint8_t env_ind_level(uint8_t which) { return which < 2 ? fk_ind[which] : 0; }
void    env_ind_set(uint8_t which, uint8_t level, bool save) {
    if (which > 1) return;
    fk_ind[which] = level > ENV_IND_MAX ? (uint8_t)ENV_IND_MAX : level;
    if (save) { fk_ind_saved[which] = fk_ind[which]; fk_ind_saves++; }
}
void    env_ind_force(uint8_t which, bool on) {
    if (which > 1) return;
    fk_ind_force = on ? (uint8_t)(fk_ind_force | (1u << which)) : (uint8_t)(fk_ind_force & ~(1u << which));
}
uint8_t env_ind_forced(void) { return fk_ind_force; }
static const char *const fk_effect_names[9] = {"Solid", "Alphas/Mods", "Cycle All", "Cycle L-R", "Cycle U-D",
                                               "Jellybean", "Heatmap", "Rainfall", "Drift"};
uint8_t     env_effects(void) { return 9; }
uint8_t     env_effect_mode(uint8_t i) { return (uint8_t)(i + 1u); }   /* modes 1-9 */
const char *env_effect_name(uint8_t i) { return i < 9 ? fk_effect_names[i] : ""; }
bool        env_effect_two_tone(uint8_t mode) { return mode == 2; }   /* Alphas/Mods */
static int  fk_boots;
static bool fk_reserve, fk_boot_fail;
bool env_bootloader(void) { fk_boots++; return !fk_boot_fail; }   /* the board resets; the host carries on */
bool env_reserve(void) { return fk_reserve; }
static env_about_t fk_about = {93240u, 767u, 4017u, 3840u, 1u,
                               (uint8_t)(ENV_LINK_BT | (0u << 2) | (ENV_LINK_CONNECTED << 4))};
void        env_about(env_about_t *a) { *a = fk_about; }
/* P3's Bluetooth: the live link is fk_about.link; the calls are counted and
 * do what bt_ui.c does synchronously (a select: the slot, linking, the
 * facts cleared; a pair: the select unless current, then waiting; a stop:
 * waiting cleared, and the select while advertising or retrying). */
static int     fk_bt_selects, fk_bt_pairs, fk_bt_stops, fk_bt_cancels;
static uint8_t fk_bt_last = 0xFF, fk_pf, fk_standin = 0xFF, fk_standin_pf;
static uint8_t fk_link_of(uint8_t slot, uint8_t st) { return (uint8_t)(ENV_LINK_BT | (slot << 2) | (st << 4)); }
static void    fk_select(uint8_t slot) {
    fk_about.link = fk_link_of(slot, ENV_LINK_LINKING);
    fk_pf         = 0;
}
uint8_t env_link(void) { return fk_standin != 0xFF ? fk_standin : fk_about.link; }
void    env_bt_select(uint8_t slot) {
    fk_bt_selects++;
    fk_bt_last = slot;
    if ((fk_about.link & 3u) == ENV_LINK_BT) fk_select(slot);
}
void env_bt_pair(uint8_t slot) {
    fk_bt_pairs++;
    fk_bt_last = slot;
    if ((fk_about.link & 3u) != ENV_LINK_BT) return;
    uint8_t cur = (fk_about.link >> 2) & 3u, st = (fk_about.link >> 4) & 7u;
    if (slot == cur && st == ENV_LINK_PAIRING && (fk_pf & ENV_PF_CONFIRMED)) return;
    if (slot != cur || (fk_pf & ENV_PF_SEL_LOST)) fk_select(slot);
    fk_pf |= ENV_PF_WAITING;
}
void env_bt_pair_stop(void) {
    fk_bt_stops++;
    fk_pf &= (uint8_t)~ENV_PF_WAITING;
    uint8_t st = (fk_about.link >> 4) & 7u;
    if ((fk_about.link & 3u) == ENV_LINK_BT && (st == ENV_LINK_PAIRING || (fk_pf & ENV_PF_RETRYING)))
        fk_select((fk_about.link >> 2) & 3u);
}
uint8_t fk_knob = 3;   /* the knob at rest, 11 */
uint8_t env_knob_state(void) { return fk_knob; }
void    env_bt_pair_cancel(void) {
    fk_bt_cancels++;
    fk_pf &= (uint8_t)~ENV_PF_WAITING;
}
uint8_t env_bt_pair_facts(void) { return fk_standin != 0xFF ? fk_standin_pf : fk_pf; }
void    env_bt_standin(uint8_t link, uint8_t facts) {
    fk_standin    = link;
    fk_standin_pf = facts;
}
uint32_t    env_build_hash(void) { return 0x36afff30u; }
bool        env_build_dirty(void) { return false; }
uint32_t    env_build_token(void) { return 0xef38330eu; }
const char *env_build_flavour(void) { return "dev"; }

/* The menu's tests watch every pass: the most CPU-fed bytes in one, and the
 * most rows showing the lit colour, and the cursor, at once (P1a: one at
 * most of each; codex on 541a8cbd: the cursor has its own colour and chunk). */
static bool menu_watch;
static int  menu_max_lit, menu_max_cursor;
static int lit_rows(void) {
    int n = 0;
    for (int r = 0; r < 8; r++) {
        bool lit = false;
        for (int y = 15 + 14 * r; y < 29 + 14 * r && !lit; y++)
            for (int x = 3; x <= 124 && !lit; x++) lit = fb[y][x] == MENU_LIT;
        n += lit;
    }
    return n;
}
static int cursor_rows(void) {
    int n = 0;
    for (int r = 0; r < 8; r++) {
        bool c = false;
        for (int y = 15 + 14 * r; y < 29 + 14 * r && !c; y++)
            for (int x = 0; x < 3 && !c; x++) c = fb[y][x] == MENU_CURSOR;
        n += c;
    }
    return n;
}

/* One main-loop pass as housekeeping_task_kb runs it: the task, then the pump
 * (its loss taken at the top, then the owner's operation). */
static void fw_pass(uint32_t dt) {
    fk_now += dt;
    fake_ticks += dt * (MB_TICK_HZ / 1000u);
    pass_bytes = 0;
    menu_ops_task(fk_now);
    dma_settle();
    if (take_lost()) {
        uint16_t a = po_loss(fk_now);
        menu_note_loss();
        if (a & PO_ACT_RESET_BUFFERS) menu_screen_invalidate();
    }
    if (po_owner() == PANEL_MENU) menu_pump();
    if (pass_bytes > max_pass_bytes) max_pass_bytes = pass_bytes;
    if (menu_watch && po_owner() == PANEL_MENU) {
        int l = lit_rows(), c = cursor_rows();
        if (l > menu_max_lit) menu_max_lit = l;
        if (c > menu_max_cursor) menu_max_cursor = c;
    }
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

    /* S1's F3 through op 27 sub 0: 16-19 take it with n 0; A, B and the
     * stop need F1; 3 goes F3 -> F2 -> F1. */
    CHECK(op27(0, 16, 0) == MI_BAD);   /* nothing open */
    open_fixture();
    CHECK(op27(0, 16, 0) == MI_OK && fx_screen() == FX_SCREEN_F3 && fx_pattern() == FX_MONO_FIRST);
    CHECK(op27(0, 19, 0) == MI_OK && fx_pattern() == FX_MONO_FIRST + 3);
    CHECK(op27(0, 20, 0) == MI_BAD && op27(0, 15, 0) == MI_BAD && op27(0, 17, 1) == MI_BAD);
    CHECK(op27(0, 0, 0) == MI_BAD && op27(0, 1, 0) == MI_BAD && op27(0, 2, 5) == MI_BAD);
    for (int i = 0; i < 400 && !(ms_settled() && !mb_busy()); i++) fw_pass(5);
    CHECK(ms_settled() && f3_mismatches(3, fx_cursor()) == 0);
    CHECK(op27(0, 3, 0) == MI_OK && fx_screen() == FX_SCREEN_F2);
    CHECK(op27(0, 3, 0) == MI_OK && fx_screen() == FX_SCREEN_F1);
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

/* --- P1a: the menu (plans/CONFIG-MENU-P1-DESIGN.md) ---------------------------
 * Driven as the board's scripts drive it, op 27 subs 11, 1, 2 and 3 through
 * the production menu_ops; every expected row is spelled out here and drawn
 * from the face, not from menu.c. */

/* A text slot at y: the cells from x 4 in fg on black, x 0-3 and 124 black
 * but for the cursor's columns 0-2 in x 0-2, in MENU_CURSOR, when `cursor`. */
/* P3: as text_slot_bad(), but cells 0-1 (x 4-15) in icon_fg when it isn't 0
 * (the current slot's status icon, in a colour of its own). text_slot_bad()
 * expects the saved option's check box in green, on every page, and the top
 * level's icons (I_POWER to I_CONN, the face's 0x8c-0x9d, and P4's I_BATT) in white, and on
 * the selected row (the cursor's) in #FFF7C6 (JD, 10-25). */
static int text_slot_bad2(uint16_t y, const char *cells, uint16_t fg, bool cursor, uint16_t icon_fg);
static int text_slot_bad(uint16_t y, const char *cells, uint16_t fg, bool cursor) {
    uint8_t c0 = (uint8_t)cells[0];
    return text_slot_bad2(y, cells, fg, cursor,
                          !strncmp(cells, FONT_MONO_CHECK_BOX, 2)                         ? 0x468Cu
                          : (c0 >= (uint8_t)FONT_MONO_I_POWER[0] && c0 <= (uint8_t)FONT_MONO_I_CONN[1]) ||
                                    c0 == (uint8_t)FONT_MONO_I_BATT[0]
                              ? (cursor ? 0xFFB8u : MENU_WHITE)
                              : 0);
}
static int text_slot_bad2(uint16_t y, const char *cells, uint16_t fg, bool cursor, uint16_t icon_fg) {
    int            bad = 0;
    size_t         len = strlen(cells);
    const uint8_t *cg  = font_small_mono[95 + (uint8_t)FONT_MONO_CURSOR[0] - 0x80];
    for (uint16_t r = 0; r < 14; r++)
        for (uint16_t x = 0; x <= 124; x++) {
            uint16_t want = 0;
            if (x < 3) {
                if (cursor && (cg[r] & (0x80 >> x))) want = MENU_CURSOR;   /* its own colour (JD, 10-24) */
            } else if (x >= 4 && x <= 123) {
                size_t  cell = (size_t)(x - 4) / 6;
                uint8_t code = cell < len ? (uint8_t)cells[cell] : (uint8_t)' ';
                const uint8_t *g = code >= 0x80 && code < 0x80 + FONT_MONO_N - 95 ? font_small_mono[95 + code - 0x80]
                                 : code >= 0x20 && code < 0x7F ? font_small_mono[code - 0x20]
                                                               : font_small_mono['?' - 0x20];
                if (g[r] & (0x80 >> ((x - 4) % 6))) want = icon_fg && cell < 2 ? icon_fg : fg;
            }
            if (fb[y + r][x] != want) bad++;
        }
    return bad;
}
/* A row's 20 cells: the label left, the value right. */
static const char *cells2(const char *label, const char *value) {
    static char out[21];
    memset(out, ' ', 20);
    out[20] = '\0';
    memcpy(out, label, strlen(label));
    memcpy(out + 20 - strlen(value), value, strlen(value));
    return out;
}
/* A list row: the cursor with the lit colour. */
static int row_bad(int r, const char *cells, uint16_t fg) {
    return text_slot_bad((uint16_t)(15 + 14 * r), cells, fg, fg == MENU_LIT);
}
static int title_bad(const char *t) { return text_slot_bad(0, t, MENU_WHITE, false); }
static void m_settle(void) {
    for (int i = 0; i < 3000 && !(ms_settled() && !mb_busy()); i++) fw_pass(5);
    CHECK(ms_settled());
}
static void m_click(void) {
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 300) == MI_ST_DONE);
    m_settle();
}
static void m_turn(int n) {
    CHECK(op27(1, n, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 300) == MI_ST_DONE);
    m_settle();
}
static void m_hold(void) {
    CHECK(op27(3, 0, 0) == MI_OK);   /* 650 ms */
    CHECK(wait_terminal(rpt[6], 400) == MI_ST_DONE);
    m_settle();
}
static uint8_t sub5_screen(void) { op27(5, 0, 0); return rpt[14]; }
static uint8_t sub5_cursor(void) { op27(5, 0, 0); return rpt[15]; }

/* The top level's rows (P4, JD 10-25: Battery under Clock, Diagnostics
 * under Bootloader on page two): their indices, and each row's cells with
 * the defaults' values. */
enum { T_LIGHT = 0, T_SCREEN, T_CONN, T_POWER, T_IND, T_CLOCK, T_BATT, T_BOOT, T_DIAG, T_HELP, T_ABOUT, T_EXIT, T_ROWS };
static const char *const top_rows_want[T_ROWS][2] = {
    {FONT_MONO_I_LIGHT " Lighting", FONT_MONO_TRI_R}, {FONT_MONO_I_SCREEN "Screen", "52%"},   /* 52 of 100 */
    {FONT_MONO_I_CONN "Connection", "BT 1"}, {FONT_MONO_I_POWER " Power", "Balanced"},   /* P3: the link */
    {FONT_MONO_I_IND "Indicators", FONT_MONO_TRI_R},  {FONT_MONO_I_CLOCK "Clock", "24h"},
    {FONT_MONO_I_BATT " Battery", "Percent"}, {FONT_MONO_I_BOOT "Bootloader", FONT_MONO_TRI_R},
    {FONT_MONO_I_DIAG " Diagnostics", FONT_MONO_TRI_R},
    {FONT_MONO_I_HELP "Help", FONT_MONO_TRI_R}, {FONT_MONO_I_ABOUT "About", FONT_MONO_TRI_R}, {FONT_MONO_I_EXIT " Exit", ""},
};
static void top_frame_ok(int cursor);

static void test_menu(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    fk_power_writes = fk_clock_writes = fk_resets = 0;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;

    /* sub 11 opens the menu: the top level, row 0 lit. */
    CHECK(op27(11, 0, 0) == MI_OK && mi_last_state() == MI_ST_DONE);
    CHECK(po_owner() == PANEL_MENU && po_session() == SESSION_OPEN);
    m_settle();
    CHECK(sub5_screen() == 16 + 1 && sub5_cursor() == 0);
    CHECK(title_bad(FONT_MONO_WRENCH " Configuration") == 0);
    top_frame_ok(0);   /* P2a's eleven rows: Help, About and Exit on page two */
    CHECK(fb[20][125] == MENU_WHITE && fb[120][125] == MENU_TRACK);   /* the scrollbar: the thumb at the top */
    CHECK(op27(0, 1, 0) == MI_BAD);                  /* sub 0 is the fixture's only */

    /* Moves: down, a wrap up, and back. */
    m_turn(1);
    CHECK(sub5_cursor() == 1 && row_bad(1, cells2(FONT_MONO_I_SCREEN "Screen", "52%"), MENU_LIT) == 0 &&
          row_bad(0, cells2(FONT_MONO_I_LIGHT " Lighting", FONT_MONO_TRI_R), MENU_DIM) == 0);
    m_turn(-2);
    CHECK(sub5_cursor() == T_EXIT);
    top_frame_ok(T_EXIT);   /* page two */
    /* Its thumb at the track's end: 75 px of 112 for twelve rows (P4), y 52-126 (codex: it was drawn off the panel). */
    CHECK(fb[51][125] == MENU_TRACK && fb[52][125] == MENU_WHITE && fb[126][125] == MENU_WHITE);
    m_turn(1);
    CHECK(sub5_cursor() == 0);

    /* Power: the choice opens on the saved option, its bullet in cell 0. */
    m_turn(T_POWER);
    m_click();
    CHECK(sub5_screen() == 16 + 2 && sub5_cursor() == 2 && title_bad(FONT_MONO_I_POWER " Power") == 0);
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
    CHECK(row_bad(1, "  Always on", MENU_DIM) == 0);   /* the bullet's cell, then a space: JD's breathing room */
    CHECK(row_bad(2, FONT_MONO_CHECK_BOX "Balanced", MENU_LIT) == 0);
    CHECK(row_bad(4, "  Lights out", MENU_DIM) == 0);
    m_turn(2);   /* Lights out */
    m_click();   /* commits */
    CHECK(fk_power == 3 && fk_power_writes == 1);
    CHECK(sub5_screen() == 16 + 1 && sub5_cursor() == T_POWER);
    CHECK(title_bad("Saved") == 0 && row_bad(T_POWER, cells2(FONT_MONO_I_POWER " Power", "Lights out"), MENU_LIT) == 0);
    for (int i = 0; i < 400; i++) fw_pass(5);   /* the flash's 1.3 s */
    m_settle();
    CHECK(title_bad(FONT_MONO_WRENCH " Configuration") == 0);

    /* Clock: a cancel by Back writes nothing, and says so. */
    m_turn(T_CLOCK - T_POWER);
    m_click();
    CHECK(sub5_screen() == 16 + 3 && sub5_cursor() == 1 && row_bad(1, FONT_MONO_CHECK_BOX "24 hour", MENU_LIT) == 0 &&
          title_bad(FONT_MONO_I_CLOCK "Clock") == 0);
    m_turn(2);   /* Date: the enum's 3 */
    m_hold();
    CHECK(fk_clock == 0 && fk_clock_writes == 0 && title_bad("Cancelled") == 0 && sub5_screen() == 16 + 1);
    m_click();
    m_turn(2);
    m_click();   /* Date */
    CHECK(fk_clock == 3 && fk_clock_writes == 1 && row_bad(T_CLOCK, cells2(FONT_MONO_I_CLOCK "Clock", "Date"), MENU_LIT) == 0);

    /* An external change (Fn+B) shows at once. */
    fk_power = 0;
    m_settle();
    fw_pass(5);
    m_settle();
    CHECK(row_bad(T_POWER, cells2(FONT_MONO_I_POWER " Power", "Always on"), MENU_DIM) == 0);

    /* Help: a topic pages by 8, clamped. Shortcuts has 12 lines: its top
     * stops at 4. */
    for (int i = 0; i < 300; i++) fw_pass(5);   /* past the Saved flash */
    m_turn(T_HELP - T_CLOCK);   /* Help (page two's first row) */
    m_click();
    CHECK(sub5_screen() == 16 + 5 && sub5_cursor() == 1 && title_bad(FONT_MONO_I_HELP "Help") == 0);
    CHECK(row_bad(1, cells2("Using the menu", FONT_MONO_TRI_R), MENU_LIT) == 0);
    m_turn(2);   /* Shortcuts */
    m_click();
    CHECK(title_bad(FONT_MONO_I_HELP "Shortcuts") == 0 && sub5_cursor() == 0);
    CHECK(row_bad(0, "Fn+Q/W/E  BT slot", MENU_WHITE) == 0);
    CHECK(fb[20][125] == MENU_WHITE);   /* a scrollbar: the thumb at the top */
    /* A page step paints the scrollbar first (JD, 10-24): in the pass that
     * takes the turn, the thumb moves to the bottom while the first row
     * still shows the old text. */
    CHECK(op27(1, 1, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
    CHECK(fb[20][125] == MENU_TRACK && fb[120][125] == MENU_WHITE);
    CHECK(row_bad(0, "Fn+Q/W/E  BT slot", MENU_WHITE) == 0);
    m_settle();
    m_turn(-1);
    m_turn(1);
    CHECK(sub5_cursor() == 4 && row_bad(0, "Fn+Up/Dn  brightness", MENU_WHITE) == 0);
    CHECK(row_bad(7, "Fn+Esc    bootloader", MENU_WHITE) == 0);
    m_turn(1);
    CHECK(sub5_cursor() == 4);
    m_turn(-1);
    CHECK(sub5_cursor() == 0);
    m_click();   /* back to Help, Shortcuts' row */
    CHECK(sub5_screen() == 16 + 5 && sub5_cursor() == 3 && row_bad(3, cells2("Shortcuts", FONT_MONO_TRI_R), MENU_LIT) == 0);
    m_hold();    /* Back to the top: Help's row */
    CHECK(sub5_screen() == 16 + 1 && sub5_cursor() == T_HELP);

    /* About: the snapshot, formatted. */
    m_turn(T_ABOUT - T_HELP);
    m_click();
    CHECK(title_bad(FONT_MONO_I_ABOUT "About") == 0);
    CHECK(row_bad(0, "Firmware 36afff30", MENU_WHITE) == 0);
    CHECK(row_bad(1, "dev, 0xef38330e", MENU_WHITE) == 0);
    CHECK(row_bad(2, "Up 1d 1h 54m", MENU_WHITE) == 0);
    CHECK(row_bad(3, "Battery 76.7%", MENU_WHITE) == 0);
    CHECK(row_bad(4, "Pack 4017 mV", MENU_WHITE) == 0);
    CHECK(row_bad(5, "Left 64h of use", MENU_WHITE) == 0);
    CHECK(row_bad(6, "Mode Balanced", MENU_WHITE) == 0);
    CHECK(row_bad(7, "Link BT 1 connected", MENU_WHITE) == 0);
    /* Reopened with new facts, before its later rows paint: no stale row. */
    m_click();
    fk_about.mode = 3; fk_about.pack_mv = ENV_UNKNOWN; fk_about.batt_pm = ENV_UNKNOWN;
    CHECK(op27(2, 0, 0) == MI_OK);
    fw_pass(5); fw_pass(5);
    CHECK(op27(2, 0, 0) == MI_OK);   /* back before it's done */
    fw_pass(5); fw_pass(5);
    CHECK(op27(2, 0, 0) == MI_OK);   /* and in again */
    m_settle();
    CHECK(title_bad(FONT_MONO_I_ABOUT "About") == 0 && row_bad(6, "Mode Lights out", MENU_WHITE) == 0);
    CHECK(row_bad(3, "Battery -", MENU_WHITE) == 0 && row_bad(4, "Pack -", MENU_WHITE) == 0);
    m_click();

    /* Diagnostics: Health hands off; a click comes back to its row. */
    m_turn(T_DIAG - T_ABOUT);   /* Diagnostics */
    m_click();
    CHECK(sub5_screen() == 16 + 4 && sub5_cursor() == 1 && title_bad(FONT_MONO_I_DIAG " Diagnostics") == 0);
    m_click();
    CHECK(po_owner() == PANEL_DEBUG && po_session() == SESSION_OPEN);
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 300) == MI_ST_DONE);
    for (int i = 0; i < 50 && po_owner() != PANEL_MENU; i++) fw_pass(5);
    m_settle();
    CHECK(po_owner() == PANEL_MENU && sub5_screen() == 16 + 4 && sub5_cursor() == 1);
    CHECK(row_bad(1, cells2("Health page", FONT_MONO_TRI_R), MENU_LIT) == 0);

    /* Reset counters: the question, a click resets, the done page, back. */
    m_turn(2);
    m_click();
    CHECK(sub5_screen() == 16 + 10 && sub5_cursor() == 0 && title_bad(FONT_MONO_I_DIAG " Reset counters") == 0);
    CHECK(text_slot_bad(22, "Clear the health", MENU_WHITE, false) == 0 && text_slot_bad(86, "Hold: cancel", MENU_WHITE, false) == 0);
    m_click();
    CHECK(fk_resets == 1 && sub5_cursor() == 1 && title_bad("Counters reset") == 0);
    CHECK(text_slot_bad(22, "Counters reset.", MENU_WHITE, false) == 0 && text_slot_bad(36, "", 0, false) == 0 &&
          text_slot_bad(86, "", 0, false) == 0);
    m_click();
    CHECK(sub5_screen() == 16 + 4 && sub5_cursor() == 3 && fk_resets == 1);
    m_click();   /* again, then a hold cancels */
    m_hold();
    CHECK(fk_resets == 1 && sub5_screen() == 16 + 4 && title_bad("Cancelled") == 0);

    /* The hint: 4 s idle on a list, the title says how; a flash wins. */
    for (int i = 0; i < 300; i++) fw_pass(5);   /* past the flash */
    for (int i = 0; i < 600; i++) fw_pass(5);   /* 4.5 s idle in all */
    m_settle();
    CHECK(title_bad("Turn + Click Knob") == 0);
    for (int i = 0; i < 200; i++) fw_pass(5);   /* 5.5 s: then how to go back (JD) */
    m_settle();
    CHECK(title_bad("Hold to Go Back") == 0);
    for (int i = 0; i < 200; i++) fw_pass(5);   /* 6.5 s: the title again */
    m_settle();
    CHECK(title_bad(FONT_MONO_I_DIAG " Diagnostics") == 0);

    /* Exit closes; the session's kind with it. */
    m_hold();
    m_turn(T_EXIT - T_DIAG - 1);   /* Exit, from Diagnostics ... */
    m_turn(1);
    CHECK(sub5_cursor() == T_EXIT);
    CHECK(op27(2, 0, 0) == MI_OK);
    for (int i = 0; i < 50 && po_session() != SESSION_NONE; i++) fw_pass(5);
    CHECK(po_session() == SESSION_NONE);

    /* The 24 s timeout closes the menu too. */
    CHECK(op27(11, 0, 0) == MI_OK);
    m_settle();
    fw_pass(MI_IDLE_MS + 10);
    fw_pass(5);
    CHECK(po_session() == SESSION_NONE);

    /* Codex, P1a's code review. */
    CHECK(op27(11, 0, 0) == MI_OK);
    m_settle();
    /* 1. Fn+B and a click in one pass: Power opens on the NEW saved value. */
    m_turn(T_POWER);   /* Power */
    fk_power = 1;
    m_settle();
    fk_power = 2;
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
    m_settle();
    CHECK(sub5_screen() == 16 + 2 && sub5_cursor() == 3 && row_bad(3, FONT_MONO_CHECK_BOX "Power saver", MENU_LIT) == 0);
    /* An external change inside an open choice: the bullet moves, the cursor
     * stays; then Back by its row cancels, writing nothing. */
    fk_power = 0;
    fw_pass(5);
    m_settle();
    CHECK(sub5_cursor() == 3 && row_bad(1, FONT_MONO_CHECK_BOX "Always on", MENU_DIM) == 0 && row_bad(3, "  Power saver", MENU_LIT) == 0);
    int w0 = fk_power_writes;
    m_turn(-3);   /* to ‹ Back */
    m_click();
    CHECK(fk_power_writes == w0 && fk_power == 0 && title_bad("Cancelled") == 0 && sub5_screen() == 16 + 1);
    /* 2. A layout change in the middle of an op: the new layout's first op is
     * timed from its own start. Diagnostics, onto Reset counters, one pass
     * of its repaint, then the click. */
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_turn(T_DIAG - T_POWER);
    m_click();
    m_turn(1);   /* Camera */
    CHECK(op27(1, 1, 0) == MI_OK);   /* Reset counters */
    CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
    fw_pass(5);
    ms_meas_reset();
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
    for (int i = 0; i < 200 && ms_ops() == 0; i++) fw_pass(5);
    CHECK(ms_ops() == 1 && ms_op_max_ticks() > 0);
    m_settle();
    CHECK(sub5_screen() == 16 + 10);
    m_hold();
    /* The Camera page's return lands on its row. */
    m_turn(-1);
    m_click();
    CHECK(po_owner() == PANEL_DEBUG);
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 300) == MI_ST_DONE);
    for (int i = 0; i < 50 && po_owner() != PANEL_MENU; i++) fw_pass(5);
    m_settle();
    CHECK(sub5_screen() == 16 + 4 && sub5_cursor() == 2 && row_bad(2, cells2("Camera page", FONT_MONO_TRI_R), MENU_LIT) == 0);
    m_hold();
    /* 4. About replaced while its old rows are still committed: Back for one
     * pass, new facts, in again, at several boundaries. */
    m_turn(T_ABOUT - T_DIAG);   /* About, from Diagnostics */
    m_click();
    for (int k = 0; k < 6; k++) {
        CHECK(op27(2, 0, 0) == MI_OK);   /* Back */
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        for (int i = 0; i < k; i++) fw_pass(5);
        fk_about.mode    = (uint8_t)(k & 3u);
        fk_about.pack_mv = (uint16_t)(3500u + k);
        CHECK(op27(2, 0, 0) == MI_OK);   /* in again: About's row is the cursor's */
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        m_settle();
        char want[21];
        snprintf(want, sizeof want, "Pack %u mV", 3500u + k);
        CHECK(title_bad(FONT_MONO_I_ABOUT "About") == 0 && row_bad(4, want, MENU_WHITE) == 0);
        snprintf(want, sizeof want, "Mode %s", (const char *[]){"Always on", "Balanced", "Power saver", "Lights out"}[k & 3]);
        CHECK(row_bad(6, want, MENU_WHITE) == 0);
    }
    m_click();
    /* Every Help topic paged to its end: 7, 7, 12 and 13 lines (JD's text, 10-24), so its
     * last top is 0, 0, 4 and 5. */
    m_turn(-1);   /* Help */
    m_click();
    for (int t = 0; t < 4; t++) {
        static const uint8_t last_top[4] = {0, 0, 4, 5};
        if (t) m_turn(1);
        m_click();
        m_turn(1);
        CHECK(sub5_cursor() == last_top[t]);
        m_turn(1);
        CHECK(sub5_cursor() == last_top[t]);
        m_click();
        CHECK(sub5_cursor() == 1 + t);
    }
    m_hold();
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    /* sub 13: a colour changed live repaints the menu in it (JD tunes shades
     * on the panel); a bad index is refused; sub 12 reads the piece timing. */
    CHECK(op27(11, 0, 0) == MI_OK);
    m_settle();
    m_click();    /* Lighting: Back unselected, light red, under Effect lit */
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
    memset(rpt, 0, sizeof rpt);   /* [5] the index, [6..7] the colour: op27() takes only two args */
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = 13;
    rpt[5] = MP_LEAVE; rpt[6] = 0x00; rpt[7] = 0xF8;   /* pure red, 0xF800 */
    CHECK(menu_ops_op27(rpt, fk_now) && rpt[5] == MI_OK);
    m_settle();
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", 0xF800u) == 0 && row_bad(1, cells2("Effect", "Alphas/Mods"), MENU_LIT) == 0);
    CHECK(op27(13, MP_N, 0) == MI_BAD);
    rpt[5] = MP_LEAVE; rpt[6] = (uint8_t)MENU_LEAVE; rpt[7] = (uint8_t)(MENU_LEAVE >> 8);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = 13;
    CHECK(menu_ops_op27(rpt, fk_now) && rpt[5] == MI_OK);
    m_settle();
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
    m_hold();     /* the top, on Lighting */
    /* JD, 10-24: the squared check on the saved option (the cursor's on
     * entry), Power's icon on its heading, ◀ on Back. */
    m_turn(T_POWER);    /* Power */
    m_click();
    {
        const char *pw = (const char *[]){"Always on", "Balanced", "Power saver", "Lights out"}[fk_power & 3];
        char        want[24];
        CHECK(sub5_screen() == 16 + 2 && sub5_cursor() == 1 + (fk_power & 3));
        snprintf(want, sizeof want, "%s%s", FONT_MONO_CHECK_BOX, pw);
        CHECK(row_bad(1 + (fk_power & 3), want, MENU_LIT) == 0);
        CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
        CHECK(title_bad(FONT_MONO_I_POWER " Power") == 0);
    }
    m_hold();
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    /* sub 4 still opens the fixture, and sub 0 works on it. */
    CHECK(op27(4, 0, 0) == MI_OK && fx_screen() == FX_SCREEN_F1);
    CHECK(sub5_screen() == FX_SCREEN_F1 && op27(0, 1, 0) == MI_OK);
    CHECK(op27(4, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1);   /* one cursor, never two, and the watcher saw it */
    CHECK(max_pass_bytes <= MB_PASS_BYTES);
    CHECK(po_invariant_fail() == 0);
    if (menu_max_lit > 1) printf("menu: %d rows lit at once\n", menu_max_lit);
    menu_watch = false;
}

/* At every pass of a move's repaint: a reversal, a second move, and a send
 * given up. The frame ends right, and no pass ever shows two lit rows. */
static void top_frame_ok(int cursor) {
    const int page = cursor / 8;
    for (int r = 0; r < 8; r++) {
        int i = page * 8 + r;
        if (i >= T_ROWS) CHECK(row_bad(r, "", 0) == 0);
        else CHECK(row_bad(r, cells2(top_rows_want[i][0], top_rows_want[i][1]),
                           i == cursor ? MENU_LIT : i == T_EXIT ? MENU_LEAVE : MENU_DIM) == 0);
    }
}
static void test_menu_stress(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;
    CHECK(op27(11, 0, 0) == MI_OK);
    m_settle();
    /* How many passes a move's repaint takes, once the turn is taken. */
    CHECK(op27(1, 1, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
    int full = 0;
    while (!(ms_settled() && !mb_busy()) && full < 500) { fw_pass(5); full++; }
    m_turn(-1);
    int consumed = 0;
    for (int k = 0; k <= full; k++) {
        /* Down two, then back up one after k passes: cursor 1. */
        CHECK(op27(1, 2, 0) == MI_OK);
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        for (int i = 0; i < k; i++) fw_pass(5);
        CHECK(op27(1, -1, 0) == MI_OK);
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        m_settle();
        top_frame_ok(1);
        /* Up one after k passes of a move down: a reversal through 0. */
        CHECK(op27(1, 1, 0) == MI_OK);
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        for (int i = 0; i < k; i++) fw_pass(5);
        CHECK(op27(1, -2, 0) == MI_OK);
        CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
        m_settle();
        top_frame_ok(0);
        /* A wrap, and a send given up k passes into it (nothing sent, then a
         * prefix): the loss repaints everything. */
        for (int prefix = 0; prefix < 2; prefix++) {
            CHECK(op27(1, -1, 0) == MI_OK);   /* to Exit, wrapping */
            CHECK(wait_terminal(rpt[6], 50) == MI_ST_DONE);
            for (int i = 0; i < k; i++) fw_pass(5);
            fault_next_fill   = 1;
            fault_fill_prefix = prefix;
            m_settle();
            if (fault_next_fill == 0) consumed++;
            fault_next_fill = 0;
            top_frame_ok(T_EXIT);
            m_turn(1);
            top_frame_ok(0);
        }
    }
    CHECK(consumed >= full);
    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1 && max_pass_bytes <= MB_PASS_BYTES);
    if (menu_max_lit > 1) printf("menu stress: %d rows lit at once\n", menu_max_lit);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);   /* sub 11 closes an open menu */
    menu_watch = false;
}


/* --- P1b: Lighting, Screen and the edit transaction ---------------------------
 * (plans/CONFIG-MENU-P1-DESIGN.md, "P1b"). Screen ids are 16 + the node:
 * Lighting 40, the Screen's editor 41, Effect 42, Brightness 43, Hue 44,
 * Saturation 45, Speed or Second color 46, Lights 47. */
enum { SC_TOP = 17, SC_LIGHT = 40, SC_SCREEN, SC_EFFECT, SC_BRIGHT, SC_HUE, SC_SAT, SC_SPEED, SC_LIGHTS };

/* The big value: the string centred in 10 cells at x 14, y (each cell is a
 * big glyph, painted in big_color by the fake DMA). */
static int big_bad(uint16_t y, const char *s) {
    char   cells[11];
    size_t n = strlen(s), at = (10 - n) / 2;
    memset(cells, ' ', 10);
    cells[10] = '\0';
    memcpy(cells + at, s, n);
    int bad = 0;
    for (int c = 0; c < 10; c++)
        if (fb[y][14 + 10 * c] != big_color(cells[c]) || fb[y + 22][14 + 10 * c + 9] != big_color(cells[c])) bad++;
    return bad;
}
/* The bar for a value of max: the outline grey, filled white below the edge. */
static int bar_bad(unsigned v, unsigned max) {
    unsigned e   = 14u + (v * 100u + max / 2u) / max;
    int      bad = 0;
    for (unsigned x = 13; x <= 114; x++)
        for (unsigned y = 51; y <= 60; y++) {
            uint16_t want = (x == 13 || x == 114 || y == 51 || y == 60) ? MENU_GREY : x < e ? MENU_WHITE : 0;
            if (fb[y][x] != want) bad++;
        }
    return bad;
}
/* The hue envelope for a marker at hue a: the strip, the white line, the
 * triangle in the lit colour, black elsewhere (y 20-40, x 0-127). */
/* QMK's hsv_to_rgb_impl() (quantum/color.c), verbatim in its arithmetic,
 * with s = v = 255; and two of its values checked by hand below. */
static uint16_t t_hue565(uint8_t h) {
    uint8_t  region = (uint8_t)(h * 6 / 255), remainder = (uint8_t)((h * 2 - region * 85) * 3), r, g, b;
    uint16_t s = 255, v = 255;
    uint8_t  p = (uint8_t)((v * (255 - s)) >> 8);
    uint8_t  q = (uint8_t)((v * (255 - ((s * remainder) >> 8))) >> 8);
    uint8_t  t = (uint8_t)((v * (255 - ((s * (255 - remainder)) >> 8))) >> 8);
    switch (region) {
        case 6:
        case 0: r = (uint8_t)v; g = t; b = p; break;
        case 1: r = q; g = (uint8_t)v; b = p; break;
        case 2: r = p; g = (uint8_t)v; b = t; break;
        case 3: r = p; g = q; b = (uint8_t)v; break;
        case 4: r = t; g = p; b = (uint8_t)v; break;
        default: r = (uint8_t)v; g = p; b = q; break;
    }
    return (uint16_t)(((r & 0xF8u) << 8) | ((g & 0xFCu) << 3) | (b >> 3));
}
static int env_bad(uint8_t a) {
    int mx = 4 + (a * 120 + 128) / 256, bad = 0;
    for (int y = 20; y <= 40; y++)
        for (int x = 0; x < 128; x++) {
            int      d = x - mx;
            uint16_t want;
            if (y >= 38) want = (d < 0 ? -d : d) <= 2 - (y - 38) ? MENU_LIT : 0;
            else if (d == 0) want = MENU_WHITE;
            else if (y >= 22 && y <= 35 && x >= 4 && x <= 123) want = t_hue565((uint8_t)(((x - 4) * 256 + 60) / 120));
            else want = 0;
            if (fb[y][x] != want) bad++;
        }
    return bad;
}
static void m_open_top(void) {
    if (po_session() != SESSION_NONE) CHECK(op27(11, 0, 0) == MI_OK);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_OPEN);
    m_settle();
}

static void test_p1b(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    fk_rgb = (env_rgb_t){2, 240, 215, 86, 127, 1, 0xFF};
    fk_rgb_ee = fk_rgb; fk_rgb_dirty = false; fk_rgb_noop = 0;
    fk_lcd = fk_lcd_saved = 52; fk_lcd_saves = 0;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;

    /* The key classification: RM_* on release, UG_* on press, nothing else. */
    CHECK(me_key_domain(0x7849, false) == ME_DOM_RGB && me_key_domain(0x7849, true) == 0);
    CHECK(me_key_domain(0x784E, false) == ME_DOM_RGB && me_key_domain(0x7840, false) == ME_DOM_RGB);   /* flags, on */
    CHECK(me_key_domain(0x7827, true) == ME_DOM_RGB && me_key_domain(0x7827, false) == 0);
    CHECK(me_key_domain(0x7820, true) == ME_DOM_RGB && me_key_domain(0x782A, true) == ME_DOM_RGB);
    CHECK(me_key_domain(0x782B, true) == 0 && me_key_domain(0x782B, false) == 0 && me_key_domain(0x784F, false) == 0);

    /* Lighting: its rows, the live values as the readout writes them. */
    CHECK(t_hue565(0) == 0xF800u && t_hue565(213) == 0xF81Fu);   /* red; codex's hue 213, magenta */

    m_open_top();
    m_click();
    CHECK(sub5_screen() == SC_LIGHT && sub5_cursor() == 1 && title_bad(FONT_MONO_I_LIGHT " Lighting") == 0);
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
    CHECK(row_bad(1, cells2("Effect", "Alphas/Mods"), MENU_LIT) == 0);
    CHECK(row_bad(2, cells2("Brightness", "34%"), MENU_DIM) == 0);   /* 86 */
    CHECK(row_bad(3, cells2("Hue", "337"), MENU_DIM) == 0);          /* 240 */
    CHECK(row_bad(4, cells2("Saturation", "84%"), MENU_DIM) == 0);   /* 215 */
    CHECK(row_bad(5, cells2("Second color", "+178"), MENU_DIM) == 0);   /* Alphas/Mods: speed 127 */
    CHECK(row_bad(6, cells2("Lights", "On"), MENU_DIM) == 0);
    CHECK(row_bad(7, "", 0) == 0);

    /* Brightness: the range editor. */
    m_turn(1);
    m_click();
    CHECK(sub5_screen() == SC_BRIGHT && sub5_cursor() == 86 && me_active() && me_field() == ME_VAL);
    CHECK(title_bad(FONT_MONO_I_LIGHT " Brightness") == 0 && big_bad(22, "34%") == 0 && bar_bad(86, 255) == 0);
    CHECK(text_slot_bad(72, "Turn: change", MENU_WHITE, false) == 0 && text_slot_bad(100, "Hold: cancel", MENU_WHITE, false) == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);   /* 200 ms: the next turn isn't fast */
    /* A slow detent is the next percentage (JD, 10-25: "micro-adjustments by
     * one value/percent"): 34% (86) to 35% (89); a fast one 8%. */
    m_turn(1);
    CHECK(fk_rgb.v == 89 && !fk_rgb_dirty && big_bad(22, "35%") == 0 && bar_bad(89, 255) == 0);
    CHECK(op27(14, 0, 0) == MI_OK && rpt[6] == 1 && rpt[7] == ME_VAL && rpt[8] == 89 && rpt[9] == 86);   /* sub 14: the edit, read */
    CHECK(op27(1, 2, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* two detents in one input: fast */
    m_settle();
    CHECK(fk_rgb.v == 130 && big_bad(22, "51%") == 0);
    /* One detent within 90 ms of the last: fast; after a pause, not. */
    CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
    CHECK(fk_rgb.v == 150);   /* 59% */
    for (int i = 0; i < 40; i++) fw_pass(5);
    CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
    CHECK(fk_rgb.v == 153);   /* 60% */
    CHECK(op27(1, 16, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* clamped (sub 1: 16 at most) */
    m_settle();
    CHECK(fk_rgb.v == 255 && big_bad(22, "100%") == 0 && bar_bad(255, 255) == 0);
    /* The flush holds while the edit is open, even for a write already due. */
    fk_rgb_dirty = true;
    fk_flush();
    CHECK(fk_rgb_dirty && fk_rgb_ee.v == 86);
    m_hold();   /* cancels: the old value, back to Lighting on its row */
    CHECK(fk_rgb.v == 86 && !me_active() && sub5_screen() == SC_LIGHT && sub5_cursor() == 2);
    CHECK(title_bad("Cancelled") == 0 && row_bad(2, cells2("Brightness", "34%"), MENU_LIT) == 0);
    fk_flush();   /* the earlier write goes now, with the restored values */
    CHECK(!fk_rgb_dirty && fk_rgb_ee.v == 86);
    /* Save. */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    m_click();
    CHECK(fk_rgb.v == 89 && fk_rgb_dirty && !me_active() && title_bad("Saved") == 0);
    CHECK(sub5_screen() == SC_LIGHT && row_bad(2, cells2("Brightness", "35%"), MENU_LIT) == 0);
    fk_flush();
    CHECK(fk_rgb_ee.v == 89);

    /* The lights off: a preview, a save and a cancel still reach the values,
     * and the lights stay off (QMK's setters return early while off). */
    fk_rgb.enable = 0;
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    CHECK(fk_rgb.v == 92 && fk_rgb.enable == 0 && fk_rgb_noop == 0);   /* 36% */
    m_hold();
    CHECK(fk_rgb.v == 89 && fk_rgb.enable == 0 && fk_rgb_noop == 0);
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(-1);
    m_click();
    CHECK(fk_rgb.v == 87 && fk_rgb.enable == 0 && fk_rgb_dirty && fk_rgb_noop == 0);   /* 34% */
    fk_flush();
    CHECK(fk_rgb_ee.v == 87 && fk_rgb_ee.enable == 0);
    fk_rgb.enable = 1;

    /* An external write mid-edit (an RM key, VIA): rolled back at once, then
     * the menu pops with "Cancelled"; an LCD write doesn't touch an RGB edit. */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    CHECK(fk_rgb.v == 92);   /* 34% to 36% */
    menu_edit_external(ME_DOM_LCD);
    m_settle();
    CHECK(me_active() && fk_rgb.v == 92 && sub5_screen() == SC_BRIGHT);
    uint16_t ext0 = me_external_count();
    menu_edit_external(ME_DOM_RGB);
    CHECK(fk_rgb.v == 87 && !me_active() && me_external_count() == ext0 + 1);
    fk_rgb.v = 100;   /* the writer applies */
    fw_pass(5);
    m_settle();
    CHECK(sub5_screen() == SC_LIGHT && title_bad("Cancelled") == 0 && row_bad(2, cells2("Brightness", "39%"), MENU_LIT) == 0);
    /* Codex, P1b's code review: an external write, then a click (k 0) or a
     * turn (k 1) queued behind it in the same pass (op 27 flies one input at
     * a time). Neither may act on the rolled-back edit: no "Saved", no
     * preview over the external value; "Cancelled", the list; and the
     * cancel's pop is one target, not two. */
    for (int k = 0; k < 2; k++) {
        for (int i = 0; i < 300; i++) fw_pass(5);
        m_settle();
        CHECK(sub5_screen() == SC_LIGHT && sub5_cursor() == 2);
        m_click();
        for (int i = 0; i < 40; i++) fw_pass(5);
        m_turn(1);
        CHECK(me_active() && fk_rgb.v == 102);   /* 39% to 40% */
        fk_rgb_dirty = false;
        menu_edit_external(ME_DOM_RGB);
        fk_rgb.v = 120;   /* the writer applies */
        CHECK(op27(k ? 1 : 2, k ? 1 : 0, 0) == MI_OK);   /* queued behind the write */
        uint8_t g0 = ms_tgen();
        fw_pass(5);
        CHECK(ms_tgen() == (uint8_t)(g0 + 1));
        m_settle();
        CHECK(sub5_screen() == SC_LIGHT && title_bad("Cancelled") == 0 && !me_active());
        CHECK(fk_rgb.v == 120 && !fk_rgb_dirty);
        fk_rgb.v = 100;
    }

    /* With no edit open, an external write is a new target: the row repaints. */
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_settle();
    uint16_t ext1 = me_external_count();
    CHECK(ext1 == ext0 + 3);   /* the three above */
    fk_rgb.v = 86;
    menu_edit_external(ME_DOM_RGB);
    fw_pass(5);
    m_settle();
    CHECK(me_external_count() == ext1 && row_bad(2, cells2("Brightness", "34%"), MENU_LIT) == 0);

    /* Hue: the hue editor, the marker across band edges, the wrap. */
    fk_rgb.h = 8;   /* the marker at x 8: its triangle across bands 0 and 1 */
    m_turn(1);
    m_click();
    CHECK(sub5_screen() == SC_HUE && title_bad(FONT_MONO_I_LIGHT " Hue") == 0 && env_bad(8) == 0 && big_bad(44, "11") == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    CHECK(fk_rgb.h == 12 && env_bad(12) == 0 && big_bad(44, "16") == 0);   /* a unit a detent; the old triangle gone from band 0 */
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(-7);   /* fast, through 0: 12 - 84 wraps to 184 */
    CHECK(fk_rgb.h == 184 && env_bad(184) == 0 && big_bad(44, "258") == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(-1);   /* a reversal */
    CHECK(fk_rgb.h == 183 && env_bad(183) == 0);
    m_hold();
    CHECK(fk_rgb.h == 8 && sub5_screen() == SC_LIGHT);
    for (int i = 0; i < 300; i++) fw_pass(5);   /* past the flash, which carries over to the next screen */

    /* Second color: Alphas/Mods' speed in the hue editor, its marker at hue +
     * speed; with another effect it's Speed, a range. */
    m_turn(2);
    m_click();
    CHECK(sub5_screen() == SC_SPEED && title_bad(FONT_MONO_I_LIGHT " Second color") == 0);
    CHECK(env_bad((uint8_t)(8 + 127)) == 0 && big_bad(44, "+178") == 0);
    m_hold();
    for (int i = 0; i < 300; i++) fw_pass(5);
    fk_rgb.mode = 1;   /* Solid */
    fw_pass(5);
    m_settle();
    menu_edit_external(ME_DOM_RGB);   /* (the writer's hook; the list repaints its label) */
    fw_pass(5);
    m_settle();
    CHECK(row_bad(5, cells2("Speed", "50%"), MENU_LIT) == 0 && row_bad(1, cells2("Effect", "Solid"), MENU_DIM) == 0);
    m_click();
    CHECK(sub5_screen() == SC_SPEED && title_bad(FONT_MONO_I_LIGHT " Speed") == 0 && big_bad(22, "50%") == 0 && bar_bad(127, 255) == 0);
    m_hold();
    fk_rgb.mode = 2;
    menu_edit_external(ME_DOM_RGB);
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_settle();

    /* Effect: a previewing choice, two pages; the check on the saved effect. */
    m_turn(-4);
    m_click();
    CHECK(sub5_screen() == SC_EFFECT && sub5_cursor() == 2 && title_bad(FONT_MONO_I_LIGHT " Effect") == 0);
    CHECK(row_bad(2, FONT_MONO_CHECK_BOX "Alphas/Mods", MENU_LIT) == 0 && row_bad(1, "  Solid", MENU_DIM) == 0);
    CHECK(fb[20][125] == MENU_WHITE);   /* ten rows: a scrollbar */
    m_turn(1);
    CHECK(fk_rgb.mode == 3 && !fk_rgb_dirty && row_bad(2, FONT_MONO_CHECK_BOX "Alphas/Mods", MENU_DIM) == 0);
    m_turn(-3);   /* Back: the old effect */
    CHECK(sub5_cursor() == 0 && fk_rgb.mode == 2);
    m_turn(-1);   /* wraps to Drift, page two */
    CHECK(sub5_cursor() == 9 && fk_rgb.mode == 9 && row_bad(1, "  Drift", MENU_LIT) == 0);
    m_click();
    CHECK(fk_rgb.mode == 9 && fk_rgb_dirty && sub5_screen() == SC_LIGHT && title_bad("Saved") == 0);
    CHECK(row_bad(1, cells2("Effect", "Drift"), MENU_LIT) == 0 && row_bad(5, cells2("Speed", "50%"), MENU_DIM) == 0);
    fk_flush();
    /* Its cancel with the lights off. */
    fk_rgb.enable = 0;
    m_click();
    m_turn(2);   /* from Drift: past Back to Solid */
    CHECK(fk_rgb.mode == 1 && fk_rgb.enable == 0 && fk_rgb_noop == 0);
    m_hold();
    CHECK(fk_rgb.mode == 9 && fk_rgb.enable == 0 && sub5_screen() == SC_LIGHT && title_bad("Cancelled") == 0);
    fk_rgb.enable = 1;

    /* Lights: Off, On, the saved one checked; Off saved explicitly. */
    m_turn(5);
    m_click();
    CHECK(sub5_screen() == SC_LIGHTS && sub5_cursor() == 2 && row_bad(2, FONT_MONO_CHECK_BOX "On", MENU_LIT) == 0);
    m_turn(-1);
    CHECK(fk_rgb.enable == 0 && row_bad(1, "  Off", MENU_LIT) == 0);
    m_turn(-1);
    CHECK(fk_rgb.enable == 1);   /* Back: the old state */
    m_turn(1);
    fk_rgb_dirty = false;
    m_click();
    CHECK(fk_rgb.enable == 0 && fk_rgb_dirty && title_bad("Saved") == 0 && row_bad(6, cells2("Lights", "Off"), MENU_LIT) == 0);
    fk_flush();
    CHECK(fk_rgb_ee.enable == 0);
    fk_rgb.enable = 1;
    m_hold();   /* to the top */

    /* Screen: from the top level; 0-100 (P2b); the requested level previewed; saved. */
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_settle();
    m_turn(1);   /* Screen (row 1) */
    m_click();
    CHECK(sub5_screen() == SC_SCREEN && sub5_cursor() == 52 && title_bad(FONT_MONO_I_SCREEN "Screen") == 0);
    CHECK(big_bad(22, "52%") == 0 && bar_bad(52, 100) == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);   /* slow: 1% */
    CHECK(fk_lcd == 53 && fk_lcd_saved == 52 && big_bad(22, "53%") == 0 && bar_bad(53, 100) == 0);
    CHECK(op27(1, 2, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* two in one input: fast, 8 each */
    m_settle();
    CHECK(fk_lcd == 69 && fk_lcd_saved == 52 && big_bad(22, "69%") == 0 && bar_bad(69, 100) == 0);
    menu_edit_external(ME_DOM_RGB);   /* an RGB write: not the Screen's domain */
    fw_pass(5);
    CHECK(me_active() && fk_lcd == 69);
    m_turn(-16);
    CHECK(fk_lcd == 0 && big_bad(22, "Off") == 0);
    m_click();
    CHECK(fk_lcd == 0 && fk_lcd_saved == 0 && fk_lcd_saves == 1 && sub5_screen() == SC_TOP && sub5_cursor() == 1);
    CHECK(row_bad(1, cells2(FONT_MONO_I_SCREEN "Screen", "Off"), MENU_LIT) == 0);
    m_click();
    m_turn(12);
    menu_edit_external(ME_DOM_LCD);   /* SCR_UP mid-edit: back to the saved 0 */
    CHECK(fk_lcd == 0 && !me_active());
    fw_pass(5);
    m_settle();
    CHECK(sub5_screen() == SC_TOP && title_bad("Cancelled") == 0);

    /* The close rolls an open edit back (panel_owner's do_close). */
    m_turn(-1);   /* Lighting */
    m_click();
    m_turn(1);   /* Brightness */
    m_click();
    m_turn(3);
    CHECK(me_active() && fk_rgb.v != 86);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    CHECK(fk_rgb.v == 86 && !me_active() && po_owner() != PANEL_MENU);

    /* The backstop: an open edit outlasts 24 s idle, not 180 s. */
    m_open_top();
    m_click();
    m_turn(1);
    m_click();
    m_turn(1);
    CHECK(me_active() && fk_rgb.v == 89);
    fw_pass(MI_IDLE_MS + 10);
    fw_pass(5);
    CHECK(po_session() == SESSION_OPEN && me_active());
    fw_pass(MI_BACKSTOP_MS);
    fw_pass(5);
    CHECK(po_session() == SESSION_NONE && !me_active() && fk_rgb.v == 86);

    /* Owed (codex, P1b's code review, item 4): the fast turn across a long
     * idle and the 32-bit wrap, and re-entering an editor; a failed send and
     * a lost glyph DMA mid-band and mid-value; a close and a reopen
     * mid-paint. Each frame ends right. */
    fk_lcd = fk_lcd_saved = 52;   /* as the top level's frame expects */
    m_open_top();
    m_click();
    m_turn(1);   /* Brightness */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    CHECK(fk_rgb.v == 89);
    fw_pass(65556 - 20);   /* a 16-bit clock would read this as 20 ms */
    m_turn(1);
    CHECK(fk_rgb.v == 92);   /* a single step, not the fast 8% */
    m_hold();
    CHECK(fk_rgb.v == 86);
    m_click();   /* re-entered at once: its first turn is never fast */
    m_turn(1);
    CHECK(fk_rgb.v == 89);
    m_hold();
    fk_now = 0xFFFFFF80u;   /* just before the 32-bit wrap */
    fw_pass(5);
    m_settle();
    m_click();
    m_turn(1);
    CHECK(fk_rgb.v == 89);
    for (int i = 0; i < 30; i++) fw_pass(5);   /* across the wrap, 150 ms on */
    m_turn(1);
    CHECK(fk_rgb.v == 92);
    CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* within 90 ms, after the wrap */
    CHECK(fk_rgb.v == 112);   /* 36% + 8 */
    /* A send given up mid-band (nothing sent, then half), and a glyph's DMA
     * lost mid-value: the loss repaints everything, and the frame ends right. */
    for (int prefix = 0; prefix < 2; prefix++) {
        for (int i = 0; i < 40; i++) fw_pass(5);
        fault_next_fill   = 1;   /* armed before the turn: the first send of its repaint, a band's */
        fault_fill_prefix = prefix;
        CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
        m_settle();
        CHECK(fault_next_fill == 0);   /* the fault was met, not left over */
        fault_next_fill = 0;
        char pc[8];
        snprintf(pc, sizeof pc, "%u%%", (unsigned)((fk_rgb.v * 100u + 127u) / 255u));
        CHECK(bar_bad(fk_rgb.v, 255) == 0 && big_bad(22, pc) == 0);
    }
    for (int i = 0; i < 40; i++) fw_pass(5);
    fault_next_dma = 1;   /* armed before the turn: the repaint's first DMA, a glyph of the value */
    CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
    m_settle();
    CHECK(fault_next_dma == 0);   /* met */
    fault_next_dma = 0;
    CHECK(fk_rgb.v == 120 && bar_bad(120, 255) == 0 && big_bad(22, "47%") == 0);   /* 44% and three slow detents */
    /* Closed mid-paint, the edit rolled back; reopened, every frame right. */
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    fw_pass(5);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE && fk_rgb.v == 86);
    m_open_top();
    top_frame_ok(0);
    m_click();
    m_turn(1);
    m_click();
    CHECK(big_bad(22, "34%") == 0 && bar_bad(86, 255) == 0);
    m_hold();
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    fk_now = 1000000u;   /* off the wrap for what follows */
    fw_pass(5);

    /* The bootloader item (JD, 10-24): a confirm page; a hold cancels; a
     * click enters it (Fn+Esc's path), except on the battery's reserve. */
    fk_boots = 0; fk_reserve = false;
    m_open_top();
    m_turn(T_BOOT);   /* P2a: page one's last row */
    CHECK(sub5_cursor() == T_BOOT && row_bad(T_BOOT, cells2(FONT_MONO_I_BOOT "Bootloader", FONT_MONO_TRI_R), MENU_LIT) == 0);
    m_click();
    CHECK(sub5_screen() == 16 + 34 && sub5_cursor() == 0 && title_bad(FONT_MONO_I_BOOT "Bootloader") == 0);
    CHECK(text_slot_bad(22, "For a firmware", MENU_WHITE, false) == 0 && text_slot_bad(86, "Hold: cancel", MENU_WHITE, false) == 0);
    m_hold();
    CHECK(fk_boots == 0 && sub5_screen() == SC_TOP && sub5_cursor() == T_BOOT && title_bad("Cancelled") == 0);
    m_click();
    m_click();
    CHECK(fk_boots == 1);
    /* A release that couldn't go over the radio: not entered, "Try again", the page stays. */
    fk_boot_fail = true;
    m_click();
    CHECK(fk_boots == 2 && sub5_screen() == 16 + 34 && sub5_cursor() == 0 && title_bad("Try again") == 0);
    fk_boot_fail = false;
    m_hold();
    fk_reserve = true;
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_click();
    m_click();   /* refused: the second page */
    CHECK(fk_boots == 2 && sub5_cursor() == 1 && text_slot_bad(22, "Plug in first:", MENU_WHITE, false) == 0);
    m_click();   /* back */
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_BOOT && fk_boots == 2);
    fk_reserve = false;
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1 && max_pass_bytes <= MB_PASS_BYTES);
    CHECK(po_invariant_fail() == 0);
    menu_watch = false;
}

/* --- P2a: Indicators and the Connection stub ----------------------------------
 * (plans/CONFIG-MENU-P1-DESIGN.md, "P2a"). Screen ids: Indicators 51,
 * Connection 52, Lock lights 53, Charging light 54. */
enum { SC_IND = 16 + 35, SC_CONN, SC_LOCKS, SC_CHGL };

/* The levels and the tick (indicator_levels.h, what indicators.c's ISR runs):
 * the table's ends and order, and the sigma-delta at every level. */
static void test_ind_levels(void) {
    CHECK(ind_level_duty[0] == 0 && ind_level_duty[1] == 256 && ind_level_duty[100] == IND_FULL);
    for (int p = 1; p <= 100; p++) CHECK(ind_level_duty[p] > ind_level_duty[p - 1]);   /* every step changes the light */
    for (int p = 0; p <= 100; p++) {
        uint16_t acc = 0;
        long     ons = 0, run = 0, max_dark = 0, last_on = -1, max_space = 0;
        for (long t = 0; t < 2L * (long)IND_FULL; t++) {
            bool on = ind_sd_step(&acc, ind_level_duty[p]);
            CHECK(acc < IND_FULL);
            if (on) {
                ons++;
                if (last_on >= 0 && t - last_on > max_space) max_space = t - last_on;
                last_on = t;
                run     = 0;
            } else if (++run > max_dark) max_dark = run;
        }
        CHECK(ons == 2L * ind_level_duty[p]);   /* exact over IND_FULL ticks: the table's duty */
        if (p == 0) CHECK(ons == 0);
        else CHECK(max_dark <= IND_PWM_TICKS - 1 && max_space <= IND_PWM_TICKS);   /* never darker for longer than level 1 */
        if (p == 1) CHECK(max_space == IND_PWM_TICKS && max_dark == IND_PWM_TICKS - 1);   /* today's level 1, exactly */
    }
    /* An unlit group keeps its accumulator and shows nothing; a forced one
     * lights whatever the lock state; Caps and Win lock share the locks'. */
    uint16_t al = 100, ac = 200;
    CHECK(ind_tick_out(false, false, false, 0, &al, &ac, IND_FULL, IND_FULL) == 0 && al == 100 && ac == 200);
    CHECK(ind_tick_out(true, false, false, 0, &al, &ac, IND_FULL, IND_FULL) == 1 && al == 100 && ac == 200);
    CHECK(ind_tick_out(false, true, false, 0, &al, &ac, IND_FULL, IND_FULL) == 2);
    CHECK(ind_tick_out(false, false, false, 1, &al, &ac, IND_FULL, IND_FULL) == 3);   /* the locks' preview: both */
    CHECK(ind_tick_out(false, false, false, 2, &al, &ac, IND_FULL, IND_FULL) == 4);   /* the charging light's */
    CHECK(ind_tick_out(false, false, true, 0, &al, &ac, 0, 0) == 0);                  /* level 0: dark */
    /* The pins to write: after a restart every one, whatever the output
     * (codex: Caps at 100% was skipped and stayed dark); else the changes. */
    for (unsigned out = 0; out < 8; out++) {
        CHECK(ind_pins_to_write((uint8_t)out, IND_OUT_UNKNOWN) == 7);
        for (unsigned last = 0; last < 8; last++) CHECK(ind_pins_to_write((uint8_t)out, (uint8_t)last) == ((out ^ last) & 7u));
    }
    /* A restart with Caps full on and a retained accumulator: the first tick
     * writes Caps on, and nothing more while it holds. */
    uint8_t last = IND_OUT_UNKNOWN, pins = 0;
    al = 12000;
    for (int t = 0; t < 10; t++) {
        uint8_t out = ind_tick_out(true, false, false, 0, &al, &ac, IND_FULL, 0), w = ind_pins_to_write(out, last);
        if (t == 0) CHECK(w == 7 && out == 1);
        else CHECK(w == 0);
        for (int b = 0; b < 3; b++)
            if (w & (1u << b)) pins = (uint8_t)((pins & ~(1u << b)) | (out & (1u << b)));
        last = out;
    }
    CHECK(pins == 1);

    /* P2b: the backlight's tick and its duty in ticks. Full and zero hold the
     * pin and leave the accumulator; between, the sigma-delta, through a
     * level change with the residual kept. */
    uint16_t ab = 5000;
    CHECK(bkl_tick_pin(IND_FULL, &ab) && ab == 5000 && !bkl_tick_pin(0, &ab) && ab == 5000);
    long on = 0;
    for (long t = 0; t < (long)IND_FULL; t++) on += bkl_tick_pin(ind_level_duty[42], &ab);
    for (long t = 0; t < (long)IND_FULL; t++) on += bkl_tick_pin(ind_level_duty[1], &ab);
    CHECK(on == ind_level_duty[42] + ind_level_duty[1] || on == ind_level_duty[42] + ind_level_duty[1] + 1);
    CHECK(ind_duty_ticks(ind_level_duty[0]) == 0 && ind_duty_ticks(ind_level_duty[1]) == 1 &&
          ind_duty_ticks(ind_level_duty[100]) == IND_PWM_TICKS);
    for (int p = 0; p <= 100; p++) {   /* within half a tick, never decreasing */
        long d = (long)ind_duty_ticks(ind_level_duty[p]) * 256 - ind_level_duty[p];
        CHECK(d >= -128 && d < 128);
        if (p) CHECK(ind_duty_ticks(ind_level_duty[p]) >= ind_duty_ticks(ind_level_duty[p - 1]));
    }
    /* The old 24 levels' ticks map to the level P2b names for them: the
     * default's 5 to 42; the dim cap 37 is never dimmer than the old 4. */
    CHECK(ind_duty_ticks(ind_level_duty[42]) == 5 && ind_level_duty[37] >= 4u * 256u && ind_level_duty[36] < 4u * 256u);
}

static void test_p2a(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    fk_ind[0] = fk_ind_saved[0] = 1; fk_ind[1] = fk_ind_saved[1] = 0; fk_ind_force = 0; fk_ind_saves = 0;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;
    m_open_top();

    /* JD, 10-25: "micro-adjustments by one value/percent". Brightness from 0
     * to 100%: every slow detent shows the next percentage, none skipped or
     * repeated; then back down by 1s, and the cancel. */
    uint8_t v0 = fk_rgb.v;
    fk_rgb.v = 0;
    m_click();   /* Lighting */
    m_turn(1);   /* Brightness */
    m_click();
    for (int p = 1; p <= 100; p++) {
        for (int i = 0; i < 20; i++) fw_pass(5);   /* 100 ms: slow */
        CHECK(op27(1, 1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
        CHECK((fk_rgb.v * 100 + 127) / 255 == p);
    }
    CHECK(fk_rgb.v == 255);
    for (int p = 99; p >= 0; p--) {
        for (int i = 0; i < 20; i++) fw_pass(5);
        CHECK(op27(1, -1, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
        CHECK((fk_rgb.v * 100 + 127) / 255 == p);
    }
    m_settle();
    CHECK(fk_rgb.v == 0 && big_bad(22, "0%") == 0);
    /* And from every starting value, not only a percentage's own (codex,
     * P2a's code review): a slow detent each way moves the shown percentage
     * by exactly one, but at the ends. */
    for (int v = 0; v < 256; v++)
        for (int dir = -1; dir <= 1; dir += 2) {
            fk_rgb.v = (uint8_t)v;
            fw_pass(100);   /* past the 90 ms fast window */
            CHECK(op27(1, dir, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
            int p0 = (v * 100 + 127) / 255, want = p0 + dir < 0 ? 0 : p0 + dir > 100 ? 100 : p0 + dir;
            CHECK((fk_rgb.v * 100 + 127) / 255 == want);
        }
    m_settle();
    m_hold();
    m_hold();
    fk_rgb.v = v0;
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_settle();

    /* Indicators: a list of two value rows. */
    m_turn(T_IND);
    CHECK(sub5_cursor() == T_IND && row_bad(T_IND, cells2(FONT_MONO_I_IND "Indicators", FONT_MONO_TRI_R), MENU_LIT) == 0);
    m_click();
    CHECK(sub5_screen() == SC_IND && sub5_cursor() == 1 && title_bad(FONT_MONO_I_IND "Indicators") == 0);
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0);
    CHECK(row_bad(1, cells2("Lock lights", "1%"), MENU_LIT) == 0);
    CHECK(row_bad(2, cells2("Charging", "Off"), MENU_DIM) == 0);
    CHECK(row_bad(3, "", 0) == 0 && fb[20][125] == 0);   /* three rows: no scrollbar */

    /* Lock lights: the range editor, 0-100; the preview lights both lock LEDs. */
    m_click();
    CHECK(sub5_screen() == SC_LOCKS && sub5_cursor() == 1 && me_active() && me_field() == ME_LOCKS && fk_ind_force == 1);
    CHECK(title_bad(FONT_MONO_I_IND "Lock lights") == 0 && big_bad(22, "1%") == 0 && bar_bad(1, 100) == 0);
    CHECK(text_slot_bad(72, "Turn: change", MENU_WHITE, false) == 0 && text_slot_bad(100, "Hold: cancel", MENU_WHITE, false) == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);   /* 200 ms: not fast */
    m_turn(1);
    CHECK(fk_ind[0] == 2 && fk_ind_saved[0] == 1 && fk_ind_saves == 0 && big_bad(22, "2%") == 0 && bar_bad(2, 100) == 0);
    CHECK(op27(14, 0, 0) == MI_OK && rpt[6] == 1 && rpt[7] == ME_LOCKS && rpt[8] == 2 && rpt[9] == 1 && rpt[12] == 2 &&
          rpt[13] == 0 && rpt[14] == 1);
    CHECK(op27(1, 3, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* three detents in one input: fast, 8 each */
    m_settle();
    CHECK(fk_ind[0] == 26 && big_bad(22, "26%") == 0 && bar_bad(26, 100) == 0);
    CHECK(op27(1, -16, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* clamped at 0: Off */
    m_settle();
    CHECK(fk_ind[0] == 0 && big_bad(22, "Off") == 0 && bar_bad(0, 100) == 0);
    for (int k = 0; k < 2; k++) {
        CHECK(op27(1, 16, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);
        m_settle();
    }
    CHECK(fk_ind[0] == 100 && big_bad(22, "100%") == 0 && bar_bad(100, 100) == 0);   /* clamped at 100 */
    m_hold();   /* cancels: the old level, the preview's force gone */
    CHECK(fk_ind[0] == 1 && fk_ind_saves == 0 && fk_ind_force == 0 && !me_active());
    CHECK(sub5_screen() == SC_IND && sub5_cursor() == 1 && title_bad("Cancelled") == 0);
    CHECK(row_bad(1, cells2("Lock lights", "1%"), MENU_LIT) == 0);
    /* Save. */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    CHECK(op27(1, 2, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* fast: 1 + 16 */
    m_settle();
    m_click();
    CHECK(fk_ind[0] == 17 && fk_ind_saved[0] == 17 && fk_ind_saves == 1 && fk_ind_force == 0 && !me_active());
    CHECK(sub5_screen() == SC_IND && title_bad("Saved") == 0 && row_bad(1, cells2("Lock lights", "17%"), MENU_LIT) == 0);
    CHECK(op27(14, 0, 0) == MI_OK && rpt[6] == 0 && rpt[12] == 17 && rpt[14] == 0);
    /* A cancel after the save restores the saved level and writes nothing. */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    m_hold();
    CHECK(fk_ind[0] == 17 && fk_ind_saved[0] == 17 && fk_ind_saves == 1 && fk_ind_force == 0);

    /* Charging light: its own group and force. */
    for (int i = 0; i < 300; i++) fw_pass(5);
    m_turn(1);
    m_click();
    CHECK(sub5_screen() == SC_CHGL && me_field() == ME_CHG && fk_ind_force == 2 && big_bad(22, "Off") == 0);
    CHECK(title_bad(FONT_MONO_I_IND "Charging light") == 0);
    for (int i = 0; i < 40; i++) fw_pass(5);
    CHECK(op27(1, 7, 0) == MI_OK && wait_terminal(rpt[6], 50) == MI_ST_DONE);   /* 56 */
    m_settle();
    for (int k = 0; k < 2; k++) {
        for (int i = 0; i < 40; i++) fw_pass(5);   /* 200 ms apart: each slow */
        m_turn(1);
    }
    CHECK(fk_ind[1] == 58 && fk_ind[0] == 17 && big_bad(22, "58%") == 0);
    m_click();
    CHECK(fk_ind_saved[1] == 58 && fk_ind_saved[0] == 17 && fk_ind_force == 0);
    CHECK(sub5_cursor() == 2 && row_bad(2, cells2("Charging", "58%"), MENU_LIT) == 0);

    /* Closed mid-edit (the opener, sub 11): rolled back, the force gone. */
    m_click();
    for (int i = 0; i < 40; i++) fw_pass(5);
    m_turn(1);
    CHECK(fk_ind[1] == 59 && fk_ind_force == 2);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    CHECK(fk_ind[1] == 58 && fk_ind_force == 0 && !me_active());
    /* The backstop closes one too. */
    m_open_top();
    m_turn(T_IND);
    m_click();
    m_click();
    CHECK(fk_ind_force == 1);
    m_turn(1);
    fw_pass(MI_BACKSTOP_MS + 10);
    fw_pass(5);
    CHECK(po_session() == SESSION_NONE && fk_ind[0] == 17 && fk_ind_force == 0);

    /* The other routes out of an open indicator edit (codex, P2a's code
     * review): the debug page's handoff (enter_debug), a wake's release
     * (do_close), and a second edit opened over it (me_open's rollback). */
    m_open_top();
    m_turn(T_IND);
    m_click();
    m_click();   /* Lock lights */
    m_turn(1);
    CHECK(me_active() && fk_ind[0] == 18 && fk_ind_force == 1);
    (void)env_po_event(PO_EV_DBG_PAGE);   /* Fn+D or op 1 from the menu: Health */
    CHECK(po_owner() == PANEL_DEBUG && !me_active() && fk_ind[0] == 17 && fk_ind_force == 0);
    (void)env_po_event(PO_EV_DBG_PAGE);   /* Camera */
    (void)env_po_event(PO_EV_DBG_PAGE);   /* back to the menu */
    for (int i = 0; i < 50 && po_owner() != PANEL_MENU; i++) fw_pass(5);
    m_settle();
    CHECK(po_owner() == PANEL_MENU && fk_ind[0] == 17 && fk_ind_force == 0);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    m_open_top();
    m_turn(T_IND);
    m_click();
    m_turn(1);
    m_click();   /* Charging light */
    m_turn(1);
    CHECK(me_active() && fk_ind[1] == 59 && fk_ind_force == 2);
    (void)env_po_event(PO_EV_WAKE_WHILE_OPEN);
    (void)env_po_event(PO_EV_WAKE_RELEASED);   /* the session closes when the hold lifts */
    CHECK(po_session() == SESSION_NONE && !me_active() && fk_ind[1] == 58 && fk_ind_force == 0);
    for (int i = 0; i < 300; i++) fw_pass(5);
    me_open(ME_LOCKS);
    me_preview(40);
    CHECK(fk_ind[0] == 40 && fk_ind_force == 1);
    me_open(ME_CHG);   /* over it: the lock lights' edit rolled back, its force gone */
    CHECK(me_field() == ME_CHG && fk_ind[0] == 17 && fk_ind_force == 2 && me_saved() == 58);
    me_cancel();
    CHECK(!me_active() && fk_ind_force == 0 && fk_ind[1] == 58);

    /* Sub 15, the bench: an external writer, so it cancels an open indicator
     * edit first ("Cancelled"); a bad level is refused. */
    m_open_top();
    m_turn(T_IND);
    m_click();
    m_click();
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = 15;
    rpt[5] = 3; rpt[6] = 82; rpt[7] = 101;
    CHECK(menu_ops_op27(rpt, fk_now) && rpt[5] == MI_BAD && me_active() && fk_ind_force == 1);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = 15;
    rpt[5] = 3; rpt[6] = 82; rpt[7] = 83;
    CHECK(menu_ops_op27(rpt, fk_now) && rpt[5] == MI_OK);
    CHECK(!me_active() && fk_ind[0] == 82 && fk_ind[1] == 83 && fk_ind_force == 3 && fk_ind_saves == 2);
    fw_pass(5);
    m_settle();
    CHECK(sub5_screen() == SC_IND && title_bad("Cancelled") == 0 && row_bad(1, cells2("Lock lights", "82%"), MENU_LIT) == 0);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x76; rpt[3] = 27; rpt[4] = 15;
    rpt[5] = 0; rpt[6] = 17; rpt[7] = 58;
    CHECK(menu_ops_op27(rpt, fk_now) && rpt[5] == MI_OK && fk_ind_force == 0 && fk_ind[0] == 17);
    m_hold();
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);


    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1 && max_pass_bytes <= MB_PASS_BYTES);
    CHECK(po_invariant_fail() == PO_FAIL_WAKE_OPEN);   /* the wake while open above, recorded as it should be; nothing else */
    menu_watch = false;
}

#ifdef MENU_ENABLE
/* The production opener (MENU_ENABLE, P1a): built and run on its own, since
 * the S0 suite above expects the opener off when unarmed. */
static void knob(bool fn) {
    CHECK(menu_physical(MI_KNOB, true, fn, fk_now) == false);   /* captured */
    fw_pass(5);
    CHECK(menu_physical(MI_KNOB, false, false, fk_now) == false);   /* its release, consumed */
    fw_pass(5);
}
static void test_menu_enable(void) {
    fw_reset();
    CHECK(menu_enabled());
    /* Unarmed: Fn+knob opens the menu; again closes it. */
    knob(true);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == 16 + 1);
    m_settle();
    knob(true);
    CHECK(po_session() == SESSION_NONE);
    /* Armed: the fixture, for the S0/S1 scripts. */
    CHECK(op27(6, 1, 0) == MI_OK);
    knob(true);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == FX_SCREEN_F1 && fx_screen() == FX_SCREEN_F1);
    /* Disarming closes it; then the unarmed opener opens the menu again. */
    CHECK(op27(6, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    knob(true);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == 16 + 1);
    knob(true);
    /* A plain knob press isn't the opener: forwarded. */
    CHECK(menu_physical(MI_KNOB, true, false, fk_now) == true);
    CHECK(menu_physical(MI_KNOB, false, false, fk_now) == true);
    CHECK(po_session() == SESSION_NONE);
    /* PENDING under the wake hold: a second opener cancels it, and the next
     * session's kind is chosen afresh. */
    fk_wake_held = true;
    knob(true);
    CHECK(po_session() == SESSION_PENDING);
    knob(true);
    CHECK(po_session() == SESSION_NONE);
    fk_wake_held = false;
    CHECK(op27(4, 0, 0) == MI_OK && po_session() == SESSION_OPEN && sub5_screen() == FX_SCREEN_F1);
    CHECK(op27(4, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    /* A close and an opener with no task between: the new kind. */
    CHECK(op27(4, 0, 0) == MI_OK);
    CHECK(op27(4, 0, 0) == MI_OK);
    knob(true);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == 16 + 1);
    knob(true);
    /* From the Fn+D page with no session (DEBUG/NONE): C1 hands off to a fresh
     * menu, its top level (do_open). Then Diagnostics > Camera and its
     * return, which lands on Camera's row. */
    (void)env_po_event(PO_EV_DBG_PAGE);
    CHECK(po_owner() == PANEL_DEBUG && po_session() == SESSION_NONE);
    knob(true);
    m_settle();
    CHECK(po_owner() == PANEL_MENU && sub5_screen() == 16 + 1 && sub5_cursor() == 0);
    m_turn(T_DIAG);   /* Diagnostics */
    m_click();
    CHECK(sub5_screen() == 16 + 4 && sub5_cursor() == 1);
    m_turn(1);
    m_click();
    CHECK(po_owner() == PANEL_DEBUG && po_session() == SESSION_OPEN);
    CHECK(op27(2, 0, 0) == MI_OK);
    CHECK(wait_terminal(rpt[6], 300) == MI_ST_DONE);
    for (int i = 0; i < 50 && po_owner() != PANEL_MENU; i++) fw_pass(5);
    m_settle();
    CHECK(sub5_screen() == 16 + 4 && sub5_cursor() == 2);
    knob(true);
    CHECK(po_session() == SESSION_NONE);
    /* After a menu session, sub 5 says so: no fixture cursor; and an opener
     * refused under the animation doesn't change that (codex). */
    CHECK(sub5_cursor() == 0xFF);
    while (po_phase() == RESTORE_CLEAR || po_phase() == RESTORE_STAGES) po_restore_advance();   /* the display's part */
    po_residual_in_t rin = {0};
    (void)po_residual_next(&rin, 0);
    (void)env_po_event(PO_EV_ANIM_START);
    CHECK(po_owner() == PANEL_ANIM);
    CHECK(op27(4, 0, 0) == MI_OK && mi_last_state() == MI_ST_REFUSED);
    CHECK(sub5_cursor() == 0xFF);
    (void)env_po_event(PO_EV_ANIM_STOP);
    CHECK(po_invariant_fail() == 0);
}
#endif

/* --- P3: Connection, the Bluetooth slots and pairing --------------------------
 * (plans/CONFIG-MENU-P1-DESIGN.md, "P3"). Screen ids: Connection 52, its
 * off-BT page 55, the Pairing page 60. "Pair a device" pairs the current
 * slot (JD, 10-25). */
enum { SC_CONNINFO = 16 + 39, SC_PAIRING = 16 + 44 };
enum { PH_START = 0, PH_OPEN, PH_DONE, PH_ENDED, PH_FAILED, PH_UNSURE };

/* Connection's rows on BT: `lit` the cursor's row; the current slot's check
 * and its link's word; Pair a device naming the current slot. */
static int conn_bad(int lit, int cur, const char *word) {
    /* The current slot's icon and its colour, by its word's state (JD, 10-25):
     * idle and linked the box in green, as on every page; linking the grey
     * hourglass; advertising the blue rune; failed the red circled X. */
    static const char *const words[5] = {"", "Trying", "Pair", "Linked", "Failed"};
    static const char *const icons[5] = {FONT_MONO_CHECK_BOX, FONT_MONO_I_WAIT, FONT_MONO_I_CONN, FONT_MONO_CHECK_BOX,
                                         FONT_MONO_I_FAIL};
    static const uint16_t    colours[5] = {0x468Cu, 0x9492u, 0x3CFFu, 0x468Cu, 0xFACBu};
    int st = 0;
    for (int i = 0; i < 5; i++)
        if (!strcmp(word, words[i])) st = i;
    int bad = row_bad(0, FONT_MONO_TRI_L " Back", lit == 0 ? MENU_LIT : MENU_LEAVE);
    for (int sl = 0; sl < 3; sl++) {
        char     label[24];
        uint16_t fg = lit == 1 + sl ? MENU_LIT : MENU_DIM;
        snprintf(label, sizeof label, "%sBluetooth %d", sl == cur ? icons[st] : "  ", sl + 1);
        bad += text_slot_bad2((uint16_t)(15 + 14 * (1 + sl)), cells2(label, sl == cur ? word : ""), fg, fg == MENU_LIT,
                              sl == cur ? colours[st] : 0);
    }
    char pair[32];   /* JD, 10-25: "Pair (a )device to BT N"; the "a" doesn't fit */
    snprintf(pair, sizeof pair, "Pair device to BT %d", cur + 1);
    return bad + row_bad(4, cells2(pair, ""), lit == 4 ? MENU_LIT : MENU_DIM);
}
/* The Pairing page's four lines, at the confirm pages' y. */
static int pairing_bad(int slot, int phase) {
    static const uint16_t ys[4] = {22, 36, 72, 86};
    char        a[32], b[32];
    const char *l[4] = {a, b, "Click or hold: stop", ""};
    switch (phase) {
        case PH_START: snprintf(a, sizeof a, "Bluetooth %d", slot + 1); snprintf(b, sizeof b, "Getting ready..."); break;
        case PH_OPEN:  snprintf(a, sizeof a, "On the device, add"); snprintf(b, sizeof b, "AK820 5.1-%d", slot + 1); break;
        case PH_DONE:  snprintf(a, sizeof a, "Bluetooth %d is", slot + 1); snprintf(b, sizeof b, "connected."); break;
        case PH_ENDED: snprintf(a, sizeof a, "Pairing ended."); b[0] = '\0'; break;
        case PH_UNSURE: snprintf(a, sizeof a, "The radio didn't"); snprintf(b, sizeof b, "confirm pairing."); break;
        default:       snprintf(a, sizeof a, "Pairing didn't"); snprintf(b, sizeof b, "start. Try again."); break;
    }
    if (phase >= PH_DONE && phase != PH_UNSURE) l[2] = "Click: back";
    int bad = title_bad(FONT_MONO_I_CONN "Pairing");
    for (int i = 0; i < 4; i++) bad += text_slot_bad(ys[i], l[i], MENU_WHITE, false);
    return bad;
}
/* The link and the facts change under the menu: a pass latches them. */
static void fk_bt_set(uint8_t link, uint8_t pf) {
    fk_about.link = link;
    fk_pf         = pf;
    fw_pass(5);
    m_settle();
}
/* From a closed menu to the Pairing page, `slot` current and linked. */
static void to_pairing(int slot) {
    fk_bt_set(fk_link_of((uint8_t)slot, ENV_LINK_CONNECTED), 0);
    m_open_top();
    m_turn(T_CONN);
    m_click();
    CHECK(sub5_screen() == SC_CONN && sub5_cursor() == 1 + slot);
    m_turn(4 - sub5_cursor());   /* Pair a device */
    m_click();
    CHECK(sub5_screen() == SC_PAIRING && (sub5_cursor() >> 4) == slot);
}

static void test_p3(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    fk_lcd = fk_lcd_saved = 52;
    fk_bt_selects = fk_bt_pairs = fk_bt_stops = fk_bt_cancels = 0;
    fk_pf = 0; fk_standin = 0xFF;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;
    const uint8_t     link0    = fk_about.link;
    const char *const words[5] = {"", "Trying", "Pair", "Linked", "Failed"};

    /* The top level's value for each link, live through the latch. */
    const struct { uint8_t link; const char *v; } tops[] = {
        {ENV_LINK_USB, "USB"}, {(uint8_t)(ENV_LINK_24G | (ENV_LINK_CONNECTED << 4)), "2.4G"},
        {fk_link_of(0, ENV_LINK_CONNECTED), "BT 1"}, {fk_link_of(1, ENV_LINK_LINKING), "BT 2"},
        {fk_link_of(2, ENV_LINK_REJECTED), "BT 3"},
    };
    m_open_top();
    m_turn(T_CONN);
    for (size_t k = 0; k < sizeof tops / sizeof tops[0]; k++) {
        fk_bt_set(tops[k].link, 0);
        CHECK(row_bad(T_CONN, cells2(FONT_MONO_I_CONN "Connection", tops[k].v), MENU_LIT) == 0);
    }

    /* Off BT (USB, then 2.4G): JD's page, and back by a click or a hold. */
    static const uint16_t    info_y[4] = {22, 36, 50, 86};
    static const char *const info[4]   = {"Switch to BT mode to", "change Bluetooth", "settings.", "Click: back"};
    for (int k = 0; k < 2; k++) {
        fk_bt_set(k ? tops[1].link : tops[0].link, 0);
        m_click();
        CHECK(sub5_screen() == SC_CONNINFO && title_bad(FONT_MONO_I_CONN "Connection") == 0);
        for (int i = 0; i < 4; i++) CHECK(text_slot_bad(info_y[i], info[i], MENU_WHITE, false) == 0);
        if (k) m_hold();
        else m_click();
        CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_CONN && title_bad("Cancelled") != 0);
    }
    /* Its cursor is 0, whatever Reset counters' page was (codex). */
    m_turn(T_DIAG - T_CONN);
    m_click();
    m_turn(2);
    m_click();
    m_click();   /* reset: its second page */
    m_click();
    m_hold();
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_DIAG);
    m_turn(T_CONN - T_DIAG);
    m_click();
    CHECK(sub5_screen() == SC_CONNINFO && sub5_cursor() == 0);
    m_click();
    /* It follows the slider: BT arriving takes it back to the top level. */
    m_click();
    CHECK(sub5_screen() == SC_CONNINFO);
    fk_bt_set(fk_link_of(1, ENV_LINK_CONNECTED), 0);
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_CONN &&
          row_bad(T_CONN, cells2(FONT_MONO_I_CONN "Connection", "BT 2"), MENU_LIT) == 0);
    CHECK(fk_bt_selects == 0 && fk_bt_pairs == 0 && fk_bt_stops == 0);

    /* On BT: the list, the cursor on the current slot, its word live. */
    m_click();
    CHECK(sub5_screen() == SC_CONN && sub5_cursor() == 2 && title_bad(FONT_MONO_I_CONN "Connection") == 0);
    CHECK(conn_bad(2, 1, "Linked") == 0);
    for (uint8_t st = 0; st <= ENV_LINK_REJECTED; st++) {
        fk_bt_set(fk_link_of(1, st), 0);
        CHECK(conn_bad(2, 1, words[st]) == 0);
    }
    /* A click on the current slot: nothing while linked or linking. */
    static const uint8_t keep[2] = {ENV_LINK_CONNECTED, ENV_LINK_LINKING};
    for (int k = 0; k < 2; k++) {
        fk_bt_set(fk_link_of(1, keep[k]), ENV_PF_WAITING);   /* a pair still waiting from before */
        m_click();
        CHECK(fk_bt_selects == 0 && sub5_screen() == SC_CONN && sub5_cursor() == 2 && title_bad("Already on BT 2") == 0);
        CHECK(fk_bt_cancels == k + 1 && fk_pf == 0);   /* superseded all the same (codex) */
    }
    /* Otherwise the tap's select: rejected (the retry), advertising (the
     * cancel), idle. */
    static const uint8_t redo[3] = {ENV_LINK_REJECTED, ENV_LINK_PAIRING, ENV_LINK_IDLE};
    for (int k = 0; k < 3; k++) {
        fk_bt_set(fk_link_of(1, redo[k]), 0);
        m_click();
        CHECK(fk_bt_selects == k + 1 && fk_bt_last == 1 && sub5_screen() == SC_CONN && sub5_cursor() == 2);
        CHECK(title_bad("Now on BT 2") == 0 && conn_bad(2, 1, "Trying") == 0);
    }
    /* Linking on a select whose retries ran out unanswered: selected again
     * (codex on P3's design: "nothing" there made it permanently inert). */
    fk_bt_set(fk_link_of(1, ENV_LINK_LINKING), ENV_PF_SEL_LOST);
    m_click();
    CHECK(fk_bt_selects == 4 && fk_bt_last == 1 && title_bad("Now on BT 2") == 0 && fk_pf == 0);
    /* And connected on a lost select: a stale CONNECTED (codex's third verify). */
    fk_bt_set(fk_link_of(1, ENV_LINK_CONNECTED), ENV_PF_SEL_LOST);
    m_click();
    CHECK(fk_bt_selects == 5 && fk_bt_last == 1 && title_bad("Now on BT 2") == 0);
    /* Another slot: its select; the check moves, the cursor stays. */
    m_turn(1);
    m_click();
    CHECK(fk_bt_selects == 6 && fk_bt_last == 2 && sub5_cursor() == 3 && title_bad("Now on BT 3") == 0);
    CHECK(conn_bad(3, 2, "Trying") == 0);
    m_turn(-2);
    m_click();
    CHECK(fk_bt_selects == 7 && fk_bt_last == 0 && sub5_cursor() == 1 && conn_bad(1, 0, "Trying") == 0);
    /* Off BT under the list: the top level. */
    fk_bt_set(ENV_LINK_USB, 0);
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_CONN &&
          row_bad(T_CONN, cells2(FONT_MONO_I_CONN "Connection", "USB"), MENU_LIT) == 0);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    /* Pair a device: the current slot's (JD, 10-25), straight to its page;
     * on BT 3, linked: no select, the pair waits. */
    fk_bt_set(fk_link_of(2, ENV_LINK_CONNECTED), 0);
    m_open_top();
    m_turn(T_CONN);
    m_click();
    CHECK(sub5_cursor() == 3);
    m_turn(1);
    CHECK(sub5_cursor() == 4 && conn_bad(4, 2, "Linked") == 0);
    m_click();
    CHECK(fk_bt_pairs == 1 && fk_bt_last == 2 && fk_about.link == fk_link_of(2, ENV_LINK_CONNECTED));
    CHECK(sub5_screen() == SC_PAIRING && sub5_cursor() == (2 << 4 | PH_START) && pairing_bad(2, PH_START) == 0);
    /* Each phase from the facts. */
    const struct { uint8_t link, pf, phase; } ph[] = {
        {fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_RETRYING, PH_START},     /* sent, optimistic, unconfirmed */
        {fk_link_of(2, ENV_LINK_LINKING), ENV_PF_RETRYING, PH_START},     /* mid-attempt, still resent */
        {fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_CONFIRMED, PH_OPEN},
        {fk_link_of(2, ENV_LINK_CONNECTED), ENV_PF_CONFIRMED, PH_DONE},
        {fk_link_of(2, ENV_LINK_REJECTED), ENV_PF_CONFIRMED, PH_ENDED},   /* advertising ended, no device */
        {fk_link_of(0, ENV_LINK_PAIRING), ENV_PF_CONFIRMED, PH_ENDED},    /* another slot's */
        {fk_link_of(2, ENV_LINK_PAIRING), 0, PH_UNSURE},                  /* optimistic, the retry gave up */
        {fk_link_of(2, ENV_LINK_CONNECTED), 0, PH_FAILED},                /* the old host won the race */
        {fk_link_of(2, ENV_LINK_LINKING), ENV_PF_SEL_LOST, PH_FAILED},    /* the select was never answered */
        {fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_WAITING | ENV_PF_CONFIRMED, PH_START},
    };
    for (size_t k = 0; k < sizeof ph / sizeof ph[0]; k++) {
        fk_bt_set(ph[k].link, ph[k].pf);
        CHECK(sub5_screen() == SC_PAIRING && sub5_cursor() == (2 << 4 | ph[k].phase) && pairing_bad(2, ph[k].phase) == 0);
    }
    CHECK(fk_bt_stops == 0 && fk_bt_selects == 7);

    /* Leaving: a click while starting stops it (only the wait: no select). */
    fk_bt_set(fk_link_of(2, ENV_LINK_LINKING), ENV_PF_WAITING);
    m_click();
    CHECK(fk_bt_stops == 1 && fk_about.link == fk_link_of(2, ENV_LINK_LINKING) && fk_pf == 0);
    CHECK(sub5_screen() == SC_CONN && sub5_cursor() == 3 && title_bad("Pairing stopped") == 0 && conn_bad(3, 2, "Trying") == 0);
    /* A hold while advertising: the stop, and its select (the cancel). */
    m_turn(1);
    m_click();   /* the current slot: no select; waiting */
    CHECK(fk_bt_pairs == 2 && fk_about.link == fk_link_of(2, ENV_LINK_LINKING) && (fk_pf & ENV_PF_WAITING));
    fk_bt_set(fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_CONFIRMED);
    fw_pass(MENU_FLASH_MS);   /* the last stop's "Pairing stopped" outlasts the steps */
    m_settle();
    CHECK(pairing_bad(2, PH_OPEN) == 0);
    m_hold();
    CHECK(fk_bt_stops == 2 && fk_about.link == fk_link_of(2, ENV_LINK_LINKING));
    CHECK(sub5_screen() == SC_CONN && sub5_cursor() == 3 && title_bad("Pairing stopped") == 0);
    /* Connected, ended or failed: a click or a hold only goes back. */
    static const uint8_t done_st[3] = {ENV_LINK_CONNECTED, ENV_LINK_REJECTED, ENV_LINK_LINKING};
    static const uint8_t done_pf[3] = {ENV_PF_CONFIRMED, ENV_PF_CONFIRMED, 0};
    for (int k = 0; k < 3; k++) {
        m_turn(1);
        m_click();
        fk_bt_set(fk_link_of(2, done_st[k]), done_pf[k]);
        CHECK(sub5_cursor() == (2 << 4 | (k == 0 ? PH_DONE : k == 1 ? PH_ENDED : PH_FAILED)));
        if (k == 1) m_hold();
        else m_click();
        CHECK(fk_bt_stops == 2 && sub5_screen() == SC_CONN && sub5_cursor() == 3 && title_bad("Pairing stopped") != 0);
    }
    /* Unsure (a lost 5B 31): a click stops it; the stop's select cancels the
     * optimistic advertising. */
    m_turn(1);
    m_click();
    fk_bt_set(fk_link_of(2, ENV_LINK_PAIRING), 0);
    CHECK(sub5_cursor() == (2 << 4 | PH_UNSURE) && pairing_bad(2, PH_UNSURE) == 0);
    m_click();
    CHECK(fk_bt_stops == 3 && fk_about.link == fk_link_of(2, ENV_LINK_LINKING) && sub5_screen() == SC_CONN &&
          title_bad("Pairing stopped") == 0);
    /* Already advertising on the current slot: the page opens advertising. */
    fk_bt_set(fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_CONFIRMED);
    m_turn(1);
    m_click();
    fw_pass(MENU_FLASH_MS);   /* the stop's "Pairing stopped" outlasts the steps here */
    m_settle();
    CHECK(fk_bt_pairs == 7 && sub5_cursor() == (2 << 4 | PH_OPEN) && pairing_bad(2, PH_OPEN) == 0);

    /* The whole Pairing page has the backstop (codex: a page that turned
     * connected after 24 s would otherwise close at once); a close never
     * stops it. */
    fw_pass(MI_IDLE_MS + 10);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == SC_PAIRING);
    fk_bt_set(fk_link_of(2, ENV_LINK_LINKING), ENV_PF_RETRYING);
    fw_pass(MI_BACKSTOP_MS);
    CHECK(po_session() == SESSION_NONE && fk_bt_stops == 3);
    to_pairing(1);
    fk_bt_set(fk_link_of(1, ENV_LINK_CONNECTED), ENV_PF_CONFIRMED);
    CHECK(sub5_cursor() == (1 << 4 | PH_DONE));
    fw_pass(MI_IDLE_MS + 10);
    CHECK(po_session() == SESSION_OPEN && sub5_screen() == SC_PAIRING);
    fw_pass(MI_BACKSTOP_MS);
    CHECK(po_session() == SESSION_NONE && fk_bt_stops == 3);
    /* Fn plus a click (op 27 sub 11 here) while advertising: closed, not stopped. */
    to_pairing(0);
    fk_bt_set(fk_link_of(0, ENV_LINK_PAIRING), ENV_PF_CONFIRMED);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE && fk_bt_stops == 3);

    /* It follows the slider from the page, to the cable and to 2.4G. */
    to_pairing(0);
    fk_bt_set(ENV_LINK_USB, 0);
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_CONN);
    CHECK(row_bad(T_CONN, cells2(FONT_MONO_I_CONN "Connection", "USB"), MENU_LIT) == 0 && fk_bt_stops == 3);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    to_pairing(1);
    fk_bt_set((uint8_t)(ENV_LINK_24G | (ENV_LINK_CONNECTED << 4)), 0);
    CHECK(sub5_screen() == SC_TOP && sub5_cursor() == T_CONN);
    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);

    /* Op 27: sub 14's link and facts; sub 16's stand-in and its checks. */
    fk_about.link = fk_link_of(1, ENV_LINK_LINKING);
    fk_pf         = ENV_PF_RETRYING;
    CHECK(op27(14, 0, 0) == MI_OK && rpt[15] == fk_about.link && rpt[16] == ENV_PF_RETRYING && rpt[17] == 3);
    CHECK(op27(16, fk_link_of(2, ENV_LINK_PAIRING), ENV_PF_CONFIRMED) == MI_OK);
    CHECK(op27(14, 0, 0) == MI_OK && rpt[15] == fk_link_of(2, ENV_LINK_PAIRING) && rpt[16] == ENV_PF_CONFIRMED);
    static const int bad_links[4] = {3, 1 | (3 << 2), 1 | (5 << 4), 0x81};
    for (int k = 0; k < 4; k++) CHECK(op27(16, bad_links[k], 0) == MI_BAD);
    CHECK(op27(16, fk_link_of(0, 0), 16) == MI_BAD);
    CHECK(op27(14, 0, 0) == MI_OK && rpt[15] == fk_link_of(2, ENV_LINK_PAIRING));   /* a refused one changes nothing */
    CHECK(op27(16, 0xFF, 0) == MI_OK && op27(14, 0, 0) == MI_OK && rpt[15] == fk_about.link && rpt[16] == ENV_PF_RETRYING);

    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1 && max_pass_bytes <= MB_PASS_BYTES);
    CHECK(po_invariant_fail() == 0);
    menu_watch    = false;
    fk_about.link = link0;
    fk_pf         = 0;
}

/* --- P4: Battery, the readout in percent or hours ----------------------------
 * (plans/CONFIG-MENU-P1-DESIGN.md, "P4"). Its screen id: 16 + N_BATT (45). */
enum { SC_BATT = 16 + 45 };
static void test_p4(void) {
    fw_reset();
    fk_power = 1; fk_clock = 0;
    fk_lcd = fk_lcd_saved = 52;
    fk_batt_hours = false; fk_batt_writes = 0;
    menu_watch = true; menu_max_lit = menu_max_cursor = 0; max_pass_bytes = 0;
    CHECK(op27(11, 0, 0) == MI_OK);
    m_settle();

    /* The top level's row, under Clock: the value Percent. */
    m_turn(T_BATT);
    CHECK(sub5_cursor() == T_BATT && row_bad(T_BATT, cells2(FONT_MONO_I_BATT " Battery", "Percent"), MENU_LIT) == 0);
    top_frame_ok(T_BATT);

    /* The choice opens on the saved option, its box green. */
    m_click();
    CHECK(sub5_screen() == SC_BATT && sub5_cursor() == 1 && title_bad(FONT_MONO_I_BATT " Battery") == 0);
    CHECK(row_bad(0, FONT_MONO_TRI_L " Back", MENU_LEAVE) == 0 && row_bad(1, FONT_MONO_CHECK_BOX "Percent", MENU_LIT) == 0 &&
          row_bad(2, "  Hours of use", MENU_DIM) == 0 && row_bad(3, "", 0) == 0);

    /* A hold cancels: nothing written, and it says so. */
    m_turn(1);
    m_hold();
    CHECK(fk_batt_writes == 0 && !fk_batt_hours && title_bad("Cancelled") == 0);
    CHECK(sub5_screen() == 16 + 1 && sub5_cursor() == T_BATT);

    /* Hours of use: a click commits, flashes Saved, and the top level shows it. */
    m_click();
    m_turn(1);
    m_click();
    CHECK(fk_batt_hours && fk_batt_writes == 1 && sub5_screen() == 16 + 1 && sub5_cursor() == T_BATT);
    CHECK(title_bad("Saved") == 0 && row_bad(T_BATT, cells2(FONT_MONO_I_BATT " Battery", "Hours"), MENU_LIT) == 0);
    for (int i = 0; i < 400; i++) fw_pass(5);   /* the flash's 1.3 s */
    m_settle();

    /* Reopened, on Hours of use; then Percent again. */
    m_click();
    CHECK(sub5_screen() == SC_BATT && sub5_cursor() == 2 && row_bad(2, FONT_MONO_CHECK_BOX "Hours of use", MENU_LIT) == 0 &&
          row_bad(1, "  Percent", MENU_DIM) == 0);
    m_turn(-1);
    m_click();
    CHECK(!fk_batt_hours && fk_batt_writes == 2 && row_bad(T_BATT, cells2(FONT_MONO_I_BATT " Battery", "Percent"), MENU_LIT) == 0);
    for (int i = 0; i < 400; i++) fw_pass(5);
    m_settle();

    /* Bootloader ends page one; Diagnostics opens page two (JD, 10-25). */
    m_turn(T_BOOT - T_BATT);
    CHECK(sub5_cursor() == T_BOOT);
    top_frame_ok(T_BOOT);
    m_turn(T_DIAG - T_BOOT);
    CHECK(sub5_cursor() == T_DIAG);
    top_frame_ok(T_DIAG);
    m_click();
    CHECK(sub5_screen() == 16 + 4);   /* Diagnostics */

    CHECK(op27(11, 0, 0) == MI_OK && po_session() == SESSION_NONE);
    CHECK(menu_max_lit <= 1 && menu_max_cursor == 1 && max_pass_bytes <= MB_PASS_BYTES);
    CHECK(po_invariant_fail() == 0);
    menu_watch = false;
}

int main(int argc, char **argv) {
#ifdef MENU_ENABLE
    (void)argc; (void)argv;
    test_menu_enable();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("menu (MENU_ENABLE): all checks passed\n");
    return 0;
#endif
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
    test_menu();
    test_menu_stress();
    test_p1b();
    test_ind_levels();
    test_p2a();
    test_p3();
    test_p4();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("menu S0: all checks passed\n");
    return 0;
}
