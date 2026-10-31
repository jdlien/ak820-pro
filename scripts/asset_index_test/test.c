/* The asset index's entries are checked before the drawing trusts them
 * (plans/AUDIT-2026-10-31.md, F-018). fa_entry_ok() is lcd_bus.c's own text,
 * extracted by run.sh with the frame and flash constants and the entry's type.
 * Every shipped entry (graphics/res/flash_assets.h's twelve) must pass; the
 * crafted ones the audit describes, and their neighbours, must not. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "x_assets.inc"

static int fails;
static void want(bool ok, bool expect, const char *what) {
    printf("%s %-58s %s\n", ok == expect ? "ok  " : "FAIL", what, ok ? "kept" : "skipped");
    if (ok != expect) fails++;
}
static flash_asset_t img(uint16_t w, uint16_t h, uint32_t off) {
    flash_asset_t a = {0};
    a.fmt = 0; a.w = w; a.h = h; a.off = off;
    return a;
}
static flash_asset_t font(uint8_t cw, uint8_t ch, uint8_t count, uint32_t off) {
    flash_asset_t a = {0};
    a.fmt = 1; a.w = cw; a.h = ch; a.cell_w = cw; a.cell_h = ch; a.first = 32; a.count = count; a.off = off;
    return a;
}

int main(void) {
    flash_asset_t a;
    /* The shipped set (sizes from flash_assets.h; offsets well inside the region). */
    a = img(24, 24, 0x1000);    want(fa_entry_ok(&a), true, "a 24x24 icon");
    a = img(79, 24, 0x2000);    want(fa_entry_ok(&a), true, "the 79x24 connection row");
    a = img(128, 128, 0x3000);  want(fa_entry_ok(&a), true, "the 128x128 splash");
    a = font(6, 14, 95, 0x10000);   want(fa_entry_ok(&a), true, "the 6x14 font, 95 glyphs");
    a = font(10, 23, 95, 0x20000);  want(fa_entry_ok(&a), true, "the 10x23 font");
    a = font(15, 22, 95, 0x30000);  want(fa_entry_ok(&a), true, "the 15x22 font");
    /* Crafted or corrupt. */
    a = img(4096, 4096, 0x1000);    want(fa_entry_ok(&a), false, "an icon of 4096x4096 (the audit's 3.9 s stall)");
    a = img(129, 24, 0x1000);       want(fa_entry_ok(&a), false, "an image one column wider than the panel");
    a = img(24, 0, 0x1000);         want(fa_entry_ok(&a), false, "an image of height 0");
    a = img(24, 24, FLASH_CHIP_SIZE - FLASH_ASSET_BASE - 100); want(fa_entry_ok(&a), false, "an image running off the chip's end");
    a = img(24, 24, 0xFFFFFF);      want(fa_entry_ok(&a), false, "an offset past the chip");
    a = font(200, 14, 95, 0x10000); want(fa_entry_ok(&a), false, "a font cell wider than the panel");
    a = font(6, 14, 0, 0x10000);    want(fa_entry_ok(&a), false, "a font of no glyphs");
    a = font(6, 14, 95, 0x10000); a.w = 7; want(fa_entry_ok(&a), false, "a font whose size is not its cell's");
    a = img(24, 24, 0x1000); a.fmt = 2;   want(fa_entry_ok(&a), false, "an unknown format");
    printf("RESULT: %s\n", fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}
