/* Host check of the settings block (kb_eeconfig.c, compiled VERBATIM against
 * stubs_kbee/ and stubs/), for the menu's P2a and P4 (plans/CONFIG-MENU-P1-DESIGN.md;
 * codex on its design, point 3): the indicator levels' bytes 7 and 8 and P4's
 * battery readout (byte 9) as
 * stored, every boundary, for each field alone; a zero-filled block (QMK's
 * answer to an older version); the deferred, coalesced write; since 10-28
 * the menu's face in byte 9's bit 2, beside the readout; since 10-30 Icon
 * only, its bit 4. Built and run by run.sh. */
#include <stdio.h>
#include <string.h>
#include "quantum.h"
#include "kb_eeconfig.h"
#include "indicators.h"
#include "indicator_levels.h"

static uint32_t now_ms = 1000;

/* Byte 9 as kb_eeconfig.c reads it (10-30): garbage with any of bits 5-7,
 * both face bits, or Icon only's bit 4 beside a readout; and as it stores a
 * readout, Icon only as bit 4 alone. */
static bool    bv_garbage(int b) { return (b & 0xE0) != 0 || (b & 0x0C) == 0x0C || ((b & 0x10) && (b & 3)); }
static uint8_t bv_bits(uint8_t v) { return v == KB_BATT_VIEW_ICON ? 0x10u : v; }
uint32_t timer_read32(void) { return now_ms; }
bool     sleep_recovering(void) { return false; }

/* The kb datablock as stored, and the writes that reach it. */
static uint8_t stored[EECONFIG_KB_DATA_SIZE];
static int     writes;
uint32_t eeconfig_read_kb_datablock(void *data, uint32_t offset, uint32_t length) {
    memcpy(data, stored + offset, length);
    return length;
}
uint32_t eeconfig_update_kb_datablock(const void *data, uint32_t offset, uint32_t length) {
    memcpy(stored + offset, data, length);
    writes++;
    return length;
}

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("  FAIL line %d: ", __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

static void boot(void) { kb_eeconfig_init(); }
static void settle(void) {
    now_ms += 5000;
    kb_eeconfig_task();
}

int main(void) {
    _Static_assert(EECONFIG_KB_DATA_SIZE == 10, "the block's P4 size");
    /* Each field alone, each stored byte: 0 unset, 1 a saved Off, 2 the
     * level 1, 101 the level 100, 102 and 255 garbage (unset). */
    static const struct { uint8_t b; bool ok; uint8_t level; } cases[] = {
        {0, false, 0}, {1, true, 0}, {2, true, 1}, {51, true, 50}, {101, true, 100}, {102, false, 0}, {255, false, 0},
    };
    for (int w = IND_LOCKS; w <= IND_CHARGING; w++)
        for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
            memset(stored, 0, sizeof stored);
            stored[7 + w] = cases[i].b;
            stored[7 + (1 - w)] = 200;    /* the other field: garbage (over 101), independent */
            boot();
            uint8_t lv = 0xEE;
            bool    ok = kb_eeconfig_get_ind_level((uint8_t)w, &lv);
            CHECK(ok == cases[i].ok && (!ok || lv == cases[i].level), "field %d byte %u: %d %u", w, cases[i].b, ok, lv);
            uint8_t other = 0xEE;
            CHECK(!kb_eeconfig_get_ind_level((uint8_t)(1 - w), &other), "field %d's garbage neighbour is unset", w);
        }
    CHECK(!kb_eeconfig_get_ind_level(2, &(uint8_t){0}), "no third group");

    /* P2b: the LCD level (byte 3), 0-100 since version 6, the same +1
     * encoding: 0 unset, 1 Off, 43 the default's 42, 101 full, 102 and 255
     * garbage; the watchdog hook's poison (0x80 and up) is garbage too. */
    static const struct { uint8_t b; bool ok; uint8_t level; } lcd[] = {
        {0, false, 0}, {1, true, 0}, {2, true, 1}, {43, true, 42}, {101, true, 100}, {102, false, 0}, {0x80, false, 0},
        {255, false, 0},
    };
    for (size_t i = 0; i < sizeof lcd / sizeof lcd[0]; i++) {
        memset(stored, 0, sizeof stored);
        stored[3] = lcd[i].b;
        boot();
        uint8_t lv = 0xEE;
        bool    ok = kb_eeconfig_get_lcd_brightness(&lv);
        CHECK(ok == lcd[i].ok && (!ok || lv == lcd[i].level), "LCD byte %u: %d %u", lcd[i].b, ok, lv);
    }

    /* A zero-filled block (an older version, or after a flash): every
     * indicator field unset, so the compile-time defaults. */
    memset(stored, 0, sizeof stored);
    boot();
    uint8_t lv;
    CHECK(!kb_eeconfig_get_ind_level(IND_LOCKS, &lv) && !kb_eeconfig_get_ind_level(IND_CHARGING, &lv), "zeros: unset");

    /* Saves: deferred to the settle, coalesced, the +1 encoding; an
     * unchanged save writes nothing; Off is stored as 1; 101 is refused. */
    writes = 0;
    kb_eeconfig_set_ind_level(IND_LOCKS, 30);
    kb_eeconfig_set_ind_level(IND_LOCKS, 31);
    kb_eeconfig_set_ind_level(IND_CHARGING, 0);
    CHECK(kb_eeconfig_write_pending() && writes == 0, "deferred");
    now_ms += 4000;
    kb_eeconfig_task();
    CHECK(writes == 0, "not before the settle");
    settle();
    CHECK(writes == 1 && stored[7] == 32 && stored[8] == 1 && !kb_eeconfig_write_pending(), "one write: %d, %u %u",
          writes, stored[7], stored[8]);
    kb_eeconfig_set_ind_level(IND_LOCKS, 31);
    settle();
    CHECK(writes == 1 && !kb_eeconfig_write_pending(), "unchanged: nothing written");
    kb_eeconfig_set_ind_level(IND_LOCKS, IND_LEVEL_MAX + 1);
    CHECK(!kb_eeconfig_write_pending() && stored[7] == 32, "101 refused");
    kb_eeconfig_set_ind_level(IND_LOCKS, 100);
    settle();
    CHECK(writes == 2 && stored[7] == 101, "100 stored as 101");
    /* And read back after a reboot. */
    boot();
    CHECK(kb_eeconfig_get_ind_level(IND_LOCKS, &lv) && lv == 100, "locks after a reboot: %u", lv);
    CHECK(kb_eeconfig_get_ind_level(IND_CHARGING, &lv) && lv == 0, "charging (saved Off) after a reboot: %u", lv);
    /* The old fields keep their bytes (codex, P2a's code review: all seven,
     * seeded, not two zeros): a save of the indicators writes the block, so
     * bytes 0-6 must come back as they were. And a save left pending when a
     * menu preview is later cancelled still writes the saved level: the
     * cancel restores the live level only, never kb_eeconfig. */
    static const uint8_t old7[7] = {0x32, 0x40, 0x82, 43, 2, 150, 2};
    memset(stored, 0, sizeof stored);
    memcpy(stored, old7, sizeof old7);
    boot();
    writes = 0;
    kb_eeconfig_set_ind_level(IND_LOCKS, 30);   /* saved; a preview and its cancel touch nothing here */
    settle();
    CHECK(writes == 1 && memcmp(stored, old7, sizeof old7) == 0 && stored[7] == 31 && stored[8] == 0,
          "bytes 0-6 kept, the pending save written: %d, %u %u", writes, stored[7], stored[8]);

    /* P4: the battery readout (byte 9), its frozen encoding: 0 unset, 1
     * percent, 2 hours, 3 both (JD, 10-26), and Icon only bit 4 alone (10-30);
     * unset and garbage read percent. */
    static const struct { uint8_t b, view; } bv[] = {{0, 1}, {1, 1}, {2, 2}, {3, 3}, {4, 1}, {0x10, 4}, {0x11, 1}, {255, 1}};
    for (size_t i = 0; i < sizeof bv / sizeof bv[0]; i++) {
        memset(stored, 0, sizeof stored);
        stored[9] = bv[i].b;
        boot();
        CHECK(kb_eeconfig_get_batt_view() == bv[i].view, "batt_view byte %u", bv[i].b);
    }
    /* Saved through the deferred write, the other bytes kept; an unchanged
     * save writes nothing; percent is stored as 1, not as unset. */
    static const uint8_t old9[9] = {0x32, 0x40, 0x82, 43, 2, 150, 2, 31, 9};
    memset(stored, 0, sizeof stored);
    memcpy(stored, old9, sizeof old9);
    boot();
    writes = 0;
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_HOURS);
    CHECK(kb_eeconfig_get_batt_view() == KB_BATT_VIEW_HOURS && kb_eeconfig_write_pending() && writes == 0,
          "hours: deferred");
    settle();
    CHECK(writes == 1 && stored[9] == 2 && memcmp(stored, old9, sizeof old9) == 0, "hours stored as 2, bytes 0-8 kept");
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_HOURS);
    settle();
    CHECK(writes == 1, "unchanged: nothing written");
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_BOTH);
    settle();
    CHECK(writes == 2 && stored[9] == 3, "both stored as 3: %u", stored[9]);
    boot();
    CHECK(kb_eeconfig_get_batt_view() == KB_BATT_VIEW_BOTH, "both after a reboot");
    kb_eeconfig_set_batt_view(0);
    kb_eeconfig_set_batt_view(5);
    settle();
    CHECK(writes == 2 && stored[9] == 3, "out of range: ignored, nothing written");
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_ICON);
    settle();
    CHECK(writes == 3 && stored[9] == 0x10 && memcmp(stored, old9, sizeof old9) == 0, "icon only stored as 0x10: %u", stored[9]);
    boot();
    CHECK(kb_eeconfig_get_batt_view() == KB_BATT_VIEW_ICON, "icon only after a reboot");
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_PERCENT);
    settle();
    CHECK(writes == 4 && stored[9] == 1, "percent stored as 1: %u", stored[9]);
    boot();
    CHECK(kb_eeconfig_get_batt_view() == KB_BATT_VIEW_PERCENT, "percent after a reboot");

    /* 10-28, the Font setting (plans/MENU-8X16-PLAN.md B5): the menu's face
     * in byte 9's bit 2, set Small, and (the third face, Regular) bit 3, so
     * zeros read Large. A byte with any of bits 4-7 set (0xFF, an erased
     * block), or both face bits, is garbage as a whole: percent and Large.
     * Named bytes first, then every byte. */
    static const struct { uint8_t b, view, font; } bf[] = {
        {0x00, 1, KB_FONT_LARGE}, {0x01, 1, KB_FONT_LARGE}, {0x02, 2, KB_FONT_LARGE}, {0x03, 3, KB_FONT_LARGE},
        {0x04, 1, KB_FONT_SMALL}, {0x05, 1, KB_FONT_SMALL}, {0x06, 2, KB_FONT_SMALL}, {0x07, 3, KB_FONT_SMALL},
        {0x08, 1, KB_FONT_REGULAR}, {0x09, 1, KB_FONT_REGULAR}, {0x0A, 2, KB_FONT_REGULAR}, {0x0B, 3, KB_FONT_REGULAR},
        {0x0C, 1, KB_FONT_LARGE}, {0x0E, 1, KB_FONT_LARGE}, {0x10, 4, KB_FONT_LARGE}, {0x14, 4, KB_FONT_SMALL},
        {0x18, 4, KB_FONT_REGULAR}, {0x11, 1, KB_FONT_LARGE}, {0x13, 1, KB_FONT_LARGE}, {0x1C, 1, KB_FONT_LARGE},
        {0x20, 1, KB_FONT_LARGE}, {0x80, 1, KB_FONT_LARGE}, {0xFE, 1, KB_FONT_LARGE}, {0xFF, 1, KB_FONT_LARGE},
    };
    for (size_t i = 0; i < sizeof bf / sizeof bf[0]; i++) {
        memset(stored, 0, sizeof stored);
        stored[9] = bf[i].b;
        boot();
        CHECK(kb_eeconfig_get_batt_view() == bf[i].view && kb_eeconfig_get_font() == bf[i].font, "byte 0x%02x: %u %u",
              bf[i].b, kb_eeconfig_get_batt_view(), kb_eeconfig_get_font());
    }
    for (int b = 0; b < 256; b++) {
        memset(stored, 0, sizeof stored);
        stored[9] = (uint8_t)b;
        boot();
        bool    garbage = bv_garbage(b);
        uint8_t view    = garbage ? KB_BATT_VIEW_PERCENT : (b & 0x10) ? KB_BATT_VIEW_ICON
                        : (b & 3) == 0 ? KB_BATT_VIEW_PERCENT : (uint8_t)(b & 3);
        uint8_t font    = garbage ? KB_FONT_LARGE : (b & 4) ? KB_FONT_SMALL : (b & 8) ? KB_FONT_REGULAR : KB_FONT_LARGE;
        CHECK(kb_eeconfig_get_batt_view() == view && kb_eeconfig_get_font() == font, "every byte: 0x%02x", b);
    }
    /* Set and read in either order from zeros, each readout with each face,
     * each setter keeping the other's field; stored canonically and read
     * back after a reboot; then each changed again, the other kept. */
    for (int first = 0; first < 2; first++)
        for (uint8_t v = KB_BATT_VIEW_PERCENT; v <= KB_BATT_VIEW_ICON; v++)
            for (uint8_t f = KB_FONT_LARGE; f <= KB_FONT_REGULAR; f++) {
                memset(stored, 0, sizeof stored);
                boot();
                writes = 0;
                if (first == 0) {
                    kb_eeconfig_set_batt_view(v);
                    CHECK(kb_eeconfig_get_font() == KB_FONT_LARGE, "readout %u first: the face kept", v);
                    kb_eeconfig_set_font(f);
                } else {
                    kb_eeconfig_set_font(f);
                    CHECK(kb_eeconfig_get_batt_view() == KB_BATT_VIEW_PERCENT, "face %u first: the readout kept", f);
                    kb_eeconfig_set_batt_view(v);
                }
                CHECK(kb_eeconfig_get_batt_view() == v && kb_eeconfig_get_font() == f, "order %d, %u %u", first, v, f);
                settle();
                uint8_t want = (uint8_t)(bv_bits(v) | (f == KB_FONT_SMALL ? 4u : f == KB_FONT_REGULAR ? 8u : 0u));
                CHECK(writes == 1 && stored[9] == want, "order %d, %u %u: one write of 0x%02x, got %d 0x%02x", first, v,
                      f, want, writes, stored[9]);
                boot();
                CHECK(kb_eeconfig_get_batt_view() == v && kb_eeconfig_get_font() == f, "%u %u after a reboot", v, f);
                uint8_t v2 = (uint8_t)(v % 4u + 1u), f2 = (uint8_t)((f + 1u) % 3u);
                kb_eeconfig_set_batt_view(v2);
                CHECK(kb_eeconfig_get_font() == f, "readout %u -> %u: the face %u kept", v, v2, f);
                kb_eeconfig_set_font(f2);
                CHECK(kb_eeconfig_get_batt_view() == v2 && kb_eeconfig_get_font() == f2, "face %u -> %u: the readout kept", f,
                      f2);
                settle();
                CHECK(writes == 2 && stored[9] == (uint8_t)(bv_bits(v2) | (f2 == KB_FONT_SMALL ? 4u : f2 == KB_FONT_REGULAR ? 8u : 0u)),
                      "changed: 0x%02x", stored[9]);
            }
    /* Unchanged saves write nothing; anything but the three faces, and a
     * readout out of range, are ignored, the other field kept. */
    memset(stored, 0, sizeof stored);
    stored[9] = 0x06;   /* hours, Small */
    boot();
    writes = 0;
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_HOURS);
    kb_eeconfig_set_font(KB_FONT_SMALL);
    kb_eeconfig_set_font(3);
    kb_eeconfig_set_font(0xFF);
    kb_eeconfig_set_batt_view(0);
    kb_eeconfig_set_batt_view(5);
    CHECK(!kb_eeconfig_write_pending(), "unchanged or ignored: nothing pending");
    settle();
    CHECK(writes == 0 && stored[9] == 0x06 && kb_eeconfig_get_batt_view() == KB_BATT_VIEW_HOURS &&
          kb_eeconfig_get_font() == KB_FONT_SMALL, "unchanged or ignored: nothing written");
    /* Each setter from every garbage byte: the byte taken as 0 before any
     * compare or keep, and the canonical byte written, never an early return
     * on matching low bits (Hours over 0xFE: 0x02) nor the raw bit 2 kept
     * (Large over 0xFF: 0x00, not Small). The other bytes kept. */
    for (int b = 0x0C; b < 256; b++) {
        if (!bv_garbage(b)) continue;   /* valid */
        for (uint8_t v = KB_BATT_VIEW_PERCENT; v <= KB_BATT_VIEW_ICON; v++) {
            memcpy(stored, old9, sizeof old9);
            stored[9] = (uint8_t)b;
            boot();
            writes = 0;
            kb_eeconfig_set_batt_view(v);
            CHECK(kb_eeconfig_get_batt_view() == v && kb_eeconfig_get_font() == KB_FONT_LARGE, "0x%02x, readout %u", b, v);
            settle();
            CHECK(writes == 1 && stored[9] == bv_bits(v) && memcmp(stored, old9, sizeof old9) == 0,
                  "0x%02x, readout %u: one write of 0x%02x, got %d 0x%02x", b, v, bv_bits(v), writes, stored[9]);
        }
        for (uint8_t f = KB_FONT_LARGE; f <= KB_FONT_REGULAR; f++) {
            memcpy(stored, old9, sizeof old9);
            stored[9] = (uint8_t)b;
            boot();
            writes = 0;
            kb_eeconfig_set_font(f);
            CHECK(kb_eeconfig_get_font() == f && kb_eeconfig_get_batt_view() == KB_BATT_VIEW_PERCENT, "0x%02x, face %u", b, f);
            settle();
            uint8_t want = f == KB_FONT_SMALL ? 0x04u : f == KB_FONT_REGULAR ? 0x08u : 0x00u;
            CHECK(writes == 1 && stored[9] == want && memcmp(stored, old9, sizeof old9) == 0,
                  "0x%02x, face %u: one write of 0x%02x, got %d 0x%02x", b, f, want, writes, stored[9]);
        }
    }
    /* The two named cases on their own. */
    memset(stored, 0, sizeof stored);
    stored[9] = 0xFE;
    boot();
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_HOURS);
    settle();
    CHECK(stored[9] == 0x02, "Hours over 0xFE: 0x%02x", stored[9]);
    stored[9] = 0xFF;
    boot();
    kb_eeconfig_set_font(KB_FONT_LARGE);
    settle();
    CHECK(stored[9] == 0x00 && kb_eeconfig_get_font() == KB_FONT_LARGE, "Large over 0xFF: 0x%02x", stored[9]);

    printf("%s kbee: the settings block's indicator and battery-readout bytes, the menu's face, Icon only\n",
           failures ? "FAIL" : "ok  ");
    return failures ? 1 : 0;
}
