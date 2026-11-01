/* A blit that reads the external flash while a host-issued erase is still
 * running is repainted once the chip is idle (plans/AUDIT-2026-10-31.md,
 * F-014; first written as the audit's verify-014). The blit itself still
 * paints what MISO holds; before the fix the cell then stayed wrong until its
 * text changed, and now lcd_blit_lost_take() reports a loss once the chip
 * reads idle, so the display's existing repair repaints.
 *
 * Compiles the real graphics/lcd_bus.c (by path, unedited) against model.c.
 * The HID side is hid_protocol.c's FC_ERASE handler, reproduced line for line
 * (it is three lines; compiling hid_protocol.c would drag in the whole board):
 *     if (flash_busy()) { data[3] = FS_BUSY; return; }
 *     data[3] = flash_erase_sector(a) ? FS_OK : FS_REFUSED;
 * The display side is display.c's clock: queue_line() pushes the changed
 * digits and marks the shadow painted, and display_blit_pump() arms one per
 * pass through lcd_draw_flash_glyph_try(); the only thing that ever makes it
 * repaint a cell whose text did not change is lcd_blit_lost_take(). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "model.h"
#include "graphics/lcd_bus.h"

#define FONT_CLOCK ASSET_IOSEVKA_REGULAR_30   /* display.c:77 */
#define CLOCK_Y    58                          /* display.c:417 */
#define CELL_W 15
#define CELL_H 22
#define FONT_OFF 0x1000u
#define FIRST 0x20
#define COUNT 95
#define LCD_OFF_X 1
#define LCD_OFF_Y 2

static int fails;
#define CHECK(c, ...) do { if (c) { printf("ok   "); } else { printf("FAIL "); fails++; } printf(__VA_ARGS__); printf("\n"); } while (0)

static uint16_t glyph_px(char ch, unsigned i) {   /* a distinct, never-uniform tile per glyph */
    return (uint16_t)(0x2000u | ((unsigned)(uint8_t)ch << 5) | (i % 29u));
}
static void provision_assets(void) {
    uint8_t *f = &model_flash[FLASH_ASSET_BASE];
    memset(model_flash, 0x00, 0x8000);                 /* the stock black frame at 0x000000 */
    f[0] = 'A'; f[1] = 'K'; f[2] = 'A'; f[3] = 'S';    /* FA_MAGIC, little endian */
    f[4] = 1; f[5] = 1;                                /* version 1, one entry */
    uint8_t *e = &f[8];
    e[0] = FONT_CLOCK; e[1] = 0;
    e[2] = (uint8_t)FONT_OFF; e[3] = (uint8_t)(FONT_OFF >> 8); e[4] = (uint8_t)(FONT_OFF >> 16);
    e[5] = 1;                                          /* fmt: font */
    e[6] = CELL_W; e[7] = 0; e[8] = CELL_H; e[9] = 0;
    e[10] = CELL_W; e[11] = CELL_H; e[12] = FIRST; e[13] = COUNT;
    for (int c = FIRST; c < FIRST + COUNT; c++) {
        uint8_t *t = &f[FONT_OFF + (uint32_t)(c - FIRST) * CELL_W * CELL_H * 2u];
        for (unsigned i = 0; i < CELL_W * CELL_H; i++) {
            uint16_t p = glyph_px((char)c, i);
            t[2 * i] = (uint8_t)p; t[2 * i + 1] = (uint8_t)(p >> 8);   /* stored LO first */
        }
    }
}
/* Pixels of the cell at panel (x,y) that are not glyph ch. */
static unsigned cell_wrong(char ch, uint16_t x, uint16_t y, uint16_t *sample) {
    unsigned bad = 0;
    for (unsigned r = 0; r < CELL_H; r++)
        for (unsigned c = 0; c < CELL_W; c++) {
            uint16_t got = model_fb[y + LCD_OFF_Y + r][x + LCD_OFF_X + c];
            if (got != glyph_px(ch, r * CELL_W + c)) bad++;
            if (sample && r == 5 && c == 5) *sample = got;
        }
    return bad;
}
static unsigned rect_not(uint16_t v, uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    unsigned bad = 0;
    for (unsigned r = 0; r < h; r++)
        for (unsigned c = 0; c < w; c++) bad += model_fb[y + LCD_OFF_Y + r][x + LCD_OFF_X + c] != v;
    return bad;
}
enum { FS_OK = 0, FS_BUSY = 1, FS_REFUSED = 3 };
static int hid_fc_erase(uint32_t a) {          /* hid_protocol.c:243-245, verbatim logic */
    if (flash_busy()) return FS_BUSY;
    return flash_erase_sector(a) ? FS_OK : FS_REFUSED;
}
static void setup(void) {
    model_reset();
    provision_assets();
    lcd_init();
    CHECK(flash_assets_init(), "setup: flash_assets_init() parses the index (%u entries)", flash_assets_count());
}

static void scenario_single(void) {
    printf("\n== the stated trigger: an erase at 0xE00000, then a clock digit ==\n");
    setup();
    const uint16_t x = 40;
    uint16_t s = 0;

    /* Control: the chip idle. */
    CHECK(lcd_draw_flash_glyph_try(FONT_CLOCK, '5', x, CLOCK_Y) && lcd_blit_wait(), "control: the '5' armed and completed");
    CHECK(cell_wrong('5', x, CLOCK_Y, NULL) == 0, "control: idle chip, the cell holds '5' exactly");

    /* ak820ctl flash write 0xE00000 frames.bin: its first FC_ERASE. */
    int st = hid_fc_erase(0xE00000u);
    CHECK(st == FS_OK, "FC_ERASE 0xE00000 answered FS_OK (%d): free space, no unlock needed", st);
    model_advance_us(3000);   /* the next main-loop pass, ~3 ms later */
    CHECK(flash_busy(), "3 ms later the chip reports WIP (flash_busy() true)");

    /* The second edge: the minute rolled, '5' -> '6'. queue_line pushed the
     * digit and marked the shadow painted; the pump arms it now. */
    uint32_t ign0 = model_fstats.ignored_reads, busy0 = model_fstats.dma_from_busy_chip;
    bool armed = lcd_draw_flash_glyph_try(FONT_CLOCK, '6', x, CLOCK_Y);
    bool waited = lcd_blit_wait();
    CHECK(armed, "lcd_draw_flash_glyph_try() ARMED the blit with the chip busy (it checks only lcd_blit_busy())");
    CHECK(waited, "lcd_blit_wait() reported success");
    CHECK(model_fstats.ignored_reads == ign0 + 1, "the flash ignored that blit's READ (0x03): %u ignored READ(s)", model_fstats.ignored_reads - ign0);
    CHECK(model_fstats.dma_from_busy_chip == busy0 + 1, "the DMA streamed %u B from a chip in WIP", CELL_W * CELL_H * 2);
    unsigned bad = cell_wrong('6', x, CLOCK_Y, &s);
    printf("     the cell: %u of %u pixels are not '6' (pixel (5,5) = 0x%04X; '6' wants 0x%04X)\n",
           bad, CELL_W * CELL_H, s, glyph_px('6', 5 * CELL_W + 5));
    CHECK(bad != 0, "BUG: the minute digit was painted with high-Z MISO, not the glyph");
    bool lost = lcd_blit_lost_take();
    CHECK(!lost, "lcd_blit_lost_take() is false while the chip is still busy (the repaint would read it too)");
    CHECK(lcd_blit_timeouts() == 0, "no timeout was counted either (the DMA ran to completion)");

    /* The synchronous paths too: a band clear and a blocking text draw. */
    lcd_clear_rect(0, 83, 60, 22);
    CHECK(rect_not(0x0000, 0, 83, 60, 22) != 0, "BUG: lcd_clear_rect() during WIP did not clear to black (%u px not black)", rect_not(0x0000, 0, 83, 60, 22));
    lcd_draw_flash_text(FONT_CLOCK, 70, CLOCK_Y, "9");
    CHECK(cell_wrong('9', 70, CLOCK_Y, NULL) != 0, "BUG: lcd_draw_flash_text() during WIP painted garbage too");

    /* The erase ends: the display's next look at the loss flag repaints. */
    model_advance_us(400000);
    CHECK(!flash_busy(), "400 ms later the erase is done (flash_busy() false)");
    CHECK(lcd_blit_lost_take(), "FIX: lcd_blit_lost_take() reports the loss once the chip is idle, so the repair repaints");
    CHECK(!lcd_blit_lost_take(), "FIX: ...once: the next look finds nothing");

    /* Proof that the content was fine and only the timing was not. */
    CHECK(lcd_draw_flash_glyph_try(FONT_CLOCK, '6', x, CLOCK_Y) && lcd_blit_wait(), "a repaint of '6' with the chip idle");
    CHECK(cell_wrong('6', x, CLOCK_Y, NULL) == 0, "...paints '6' exactly");
}

/* Codex on F-014's fix: the display looks at the loss while the chip is still
 * busy, then the next blit is the first to see it idle. That blit's idle check
 * cleared the latch and dropped the mark of the blit made mid-erase, so its
 * garbage cell stayed. Whichever path sees the idle first must keep it. */
static void scenario_idle_blit_first(void) {
    printf("\n== a blit mid-erase, a look while busy, then an idle blit before the next look ==\n");
    setup();
    const uint16_t x = 40;
    CHECK(hid_fc_erase(0xE00000u) == FS_OK, "FC_ERASE 0xE00000 answered FS_OK");
    model_advance_us(3000);
    CHECK(lcd_draw_flash_glyph_try(FONT_CLOCK, '6', x, CLOCK_Y) && lcd_blit_wait(), "the '6' blitted mid-erase");
    CHECK(cell_wrong('6', x, CLOCK_Y, NULL) != 0, "...painted garbage (the chip ignored its READ)");
    CHECK(!lcd_blit_lost_take(), "a look while still busy reports nothing yet");
    model_advance_us(400000);
    CHECK(!flash_busy(), "the erase done");
    CHECK(lcd_draw_flash_glyph_try(FONT_CLOCK, '7', 70, CLOCK_Y) && lcd_blit_wait(), "another cell's blit, the first to see the chip idle");
    CHECK(cell_wrong('7', 70, CLOCK_Y, NULL) == 0, "...paints '7' exactly");
    CHECK(lcd_blit_lost_take(), "FIX: the next look still reports the mid-erase blit's loss, so the '6' is repainted");
    CHECK(!lcd_blit_lost_take(), "...once");
}

/* The whole erase phase of `ak820ctl flash write 0xE00000 <557,056 B>` (the
 * 10-28 font-test frames: 136 sectors), driven as ak820ctl drives it: one
 * FC_ERASE per HID round trip, re-sent on FS_BUSY. A clock edge each second
 * queues the seconds digit (and, on the minute, the minute digit). Each edge
 * is painted on the pass after it. Counts how many edges paint from a busy
 * chip. */
static void scenario_write_phase(uint32_t rtt_us, uint32_t erase_us) {
    setup();
    model_erase_us = erase_us;
    const uint32_t sectors = 136, start = 0xE00000u;
    uint32_t sent = 0, edges = 0, edges_bad = 0, minute_edges = 0, minute_bad = 0;
    uint32_t t0 = model_now_us(), next_edge = t0 + 1000000u - 1u;   /* the first edge almost a second in */
    unsigned secs = 0;
    while (sent < sectors) {
        int st = hid_fc_erase(start + sent * 4096u);
        if (st == FS_OK) sent++;
        else if (st != FS_BUSY) { printf("FAIL FC_ERASE refused\n"); fails++; return; }
        /* the main loop runs ~335 Hz between HID packets */
        for (uint32_t t = 0; t < rtt_us; t += 3000) {
            model_advance_us(3000);
            if (model_now_us() >= next_edge) {
                next_edge += 1000000u;
                secs++;
                char d = (char)('0' + secs % 10u);
                (void)lcd_draw_flash_glyph_try(FONT_CLOCK, d, 100, CLOCK_Y);
                (void)lcd_blit_wait();
                edges++;
                bool bad = cell_wrong(d, 100, CLOCK_Y, NULL) != 0;
                edges_bad += bad;
                if (secs % 60u == 0) { minute_edges++; minute_bad += bad; }
            }
        }
    }
    double phase_s = (model_now_us() - t0) / 1e6;
    printf("     erase %3u ms, HID round trip %2u ms: erase phase %.1f s, %u clock edges, %u painted from a busy chip (%.0f%%)\n",
           erase_us / 1000u, rtt_us / 1000u, phase_s, edges, edges_bad, edges ? 100.0 * edges_bad / edges : 0.0);
    CHECK(edges_bad > 0, "BUG: edges inside the erase phase paint garbage");
    (void)minute_edges; (void)minute_bad;
}

int main(int argc, char **argv) {
    if (argc > 1) model_hiz = (uint8_t)strtoul(argv[1], NULL, 0);
    printf("MISO high-Z modelled as 0x%02X\n", model_hiz);
    scenario_single();
    scenario_idle_blit_first();
    printf("\n== the erase phase of a 557,056 B write to 0xE00000 (136 sectors), as ak820ctl drives it ==\n");
    scenario_write_phase(2000, 45000);
    scenario_write_phase(10000, 45000);
    scenario_write_phase(10000, 300000);
    printf("\nRESULT: %s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
