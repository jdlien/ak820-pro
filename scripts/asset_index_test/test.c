/* The asset index's entries are checked before the drawing trusts them
 * (plans/AUDIT-2026-10-31.md, F-018). fa_entry_ok() is lcd_bus.c's own text,
 * extracted by run.sh with the frame and flash constants and the entry's type.
 * Every shipped entry (graphics/res/flash_assets.h's twelve) must pass; the
 * crafted ones the audit describes, and their neighbours, must not. And through
 * the loader (codex's review): the shipped blob loads whole, each id finding its
 * own entry; with its first, a middle and its last entry corrupted, those three
 * are skipped and every other id still finds its own, not a neighbour's. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void lcd_flash_init(void) {}
static void flash_read_bytes(uint32_t addr, uint8_t *buf, uint32_t n);
#include "x_assets.inc"

/* The chip's asset region, for flash_assets_init()'s reads. */
static uint8_t chip_asset[0x40000];
static void flash_read_bytes(uint32_t addr, uint8_t *buf, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) {
        uint32_t o = addr + i - FLASH_ASSET_BASE;
        buf[i] = o < sizeof chip_asset ? chip_asset[o] : 0xFF;
    }
}

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

static long load_blob(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    memset(chip_asset, 0xFF, sizeof chip_asset);
    long n = (long)fread(chip_asset, 1, sizeof chip_asset, f);
    fclose(f);
    return n;
}
static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static void check_lookups(uint8_t n, uint32_t skipped_mask) {
    for (uint8_t i = 0; i < n; i++) {
        const uint8_t *e  = &chip_asset[8 + 16 * i];
        uint16_t       id = le16(e);
        const flash_asset_t *a = flash_asset(id);
        bool skip = (skipped_mask >> i) & 1;
        bool ok   = skip ? a == NULL
                         : a && a->id == id && a->off == ((uint32_t)e[2] | ((uint32_t)e[3] << 8) | ((uint32_t)e[4] << 16)) &&
                               a->fmt == e[5] && a->w == le16(e + 6) && a->h == le16(e + 8);
        if (!ok) { printf("FAIL entry %u, id %u: %s\n", i, id, skip ? "should draw nothing" : "not its own entry"); fails++; }
    }
}

int main(int argc, char **argv) {
    flash_asset_t a;
    if (argc > 1) {
        long sz = load_blob(argv[1]);
        uint8_t n = chip_asset[5];
        bool ok = flash_assets_init();
        printf("%s the shipped index (%ld B, %u entries): loaded, %u kept\n", ok && flash_assets_count() == n ? "ok  " : "FAIL",
               sz, n, flash_assets_count());
        if (!ok || flash_assets_count() != n) fails++;
        check_lookups(n, 0);
        for (uint8_t i = 0; i < n; i++) {   /* each entry wholly inside the blob */
            const flash_asset_t *x = flash_asset(le16(&chip_asset[8 + 16 * i]));
            uint32_t bytes = x->fmt == 0 ? (uint32_t)x->w * x->h * 2u : (uint32_t)x->cell_w * x->cell_h * 2u * x->count;
            if (x->off + bytes > (uint32_t)sz) { printf("FAIL entry %u runs past the blob\n", i); fails++; }
        }
        uint8_t mid = (uint8_t)(n / 2), last = (uint8_t)(n - 1);
        chip_asset[8 + 16 * 0 + 6] = 0x00; chip_asset[8 + 16 * 0 + 7] = 0x10;        /* the first: 4096 wide */
        chip_asset[8 + 16 * mid + 5] = 7;                                              /* a middle: an unknown format */
        chip_asset[8 + 16 * last + 2] = 0xFF; chip_asset[8 + 16 * last + 3] = 0xFF;
        chip_asset[8 + 16 * last + 4] = 0xFF;                                          /* the last: past the chip */
        ok = flash_assets_init();
        printf("%s the same with entries 0, %u and %u corrupted: %u kept\n", ok && flash_assets_count() == n - 3 ? "ok  " : "FAIL",
               mid, last, flash_assets_count());
        if (!ok || flash_assets_count() != n - 3) fails++;
        check_lookups(n, 1u | (1u << mid) | (1u << last));
        if (flash_asset(LCD_FONT_SONG_LARGE) || flash_asset(LCD_FONT_SONG_REGULAR)) { printf("FAIL a song font id found\n"); fails++; }
    }
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
