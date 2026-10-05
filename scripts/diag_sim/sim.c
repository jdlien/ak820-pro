/* Host check of Phase 1b's flash-1 diagnostics: loop_acct.c (D1) and
 * flash_stats.c (C1), compiled VERBATIM against the stubs here. Each scenario
 * drives known passes or known EEPROM writes through the firmware's own entry
 * points, checks the result in C, then prints every reply page as hex so
 * test_decode.py can run hostagent/ak820health.py's decoders over the bytes
 * the firmware itself filled. Build and run with run.sh. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "quantum.h"
#include "ch.h"
#include "loop_acct.h"
#include "flash_stats.h"

static uint32_t now_ms = 20000;
static uint16_t now_tick;
uint32_t  timer_read32(void) { return now_ms; }
systime_t chVTGetSystemTimeX(void) { return now_tick; }

/* The emulated EEPROM's cache, as the hook reads it. */
static uint8_t eeprom[1024];
uint8_t eeprom_read_byte(const uint8_t *addr) { return eeprom[(uintptr_t)addr]; }
void eeprom_wear_leveling_write_hook(uint32_t addr, const void *buf, size_t len);

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("  FAIL line %d: ", __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

static void dump(const char *cmd, uint8_t page, bool (*fill)(uint8_t, uint8_t *)) {
    uint8_t out[28];
    if (!fill(page, out)) return;
    printf("PAGE %s %u ", cmd, page);
    for (int i = 0; i < 28; i++) printf("%02x", out[i]);
    printf("\n");
}

/* One scope of `ticks` system ticks, through the real ACCT() macro. */
static void spend(uint8_t scope, uint16_t ticks) {
    ACCT(scope, now_tick += ticks);
}

/* A pass: scopes as given, the rest unaccounted, closed at gap_ms. */
static void pass(uint32_t gap_ms) {
    now_ms += gap_ms;
    loop_acct_pass_end(gap_ms);
}

static void acct(void) {
    /* 100 fast passes: 1 ms of CH582, 3 ms in all. */
    for (int i = 0; i < 100; i++) { spend(ACCT_CH582, 188); pass(3); }
    /* A slow pass made of two scopes: 8 ms display + 3 ms battery, 12 ms long
     * -> 1 ms unaccounted. 8 ms = 1500 ticks, 3 ms = 562.5 -> 563. */
    spend(ACCT_DISP_HK, 1500); spend(ACCT_BATT, 563); pass(12);
    /* A slow pass that is all unaccounted (QMK's own work). */
    pass(20);
    /* A pass of exactly 10 ms counts as slow; 9 ms does not. */
    spend(ACCT_RTC, 1875); pass(10);
    spend(ACCT_RTC, 1688); pass(9);

    uint8_t p[28];
    loop_acct_fill(0, p);
    uint32_t passes = p[4] | p[5] << 8 | p[6] << 16 | (uint32_t)p[7] << 24;
    uint32_t slow   = p[8] | p[9] << 8 | p[10] << 16 | (uint32_t)p[11] << 24;
    CHECK(passes == 104, "passes %u", passes);
    CHECK(slow == 3, "slow passes %u (12, 20 and 10 ms; not 9)", slow);
    /* The 12 ms pass's ring entry: display 8, battery 3, unaccounted 1. */
    loop_acct_fill(16, p);
    CHECK(p[4] == 12 && p[5 + ACCT_DISP_HK] == 8 && p[5 + ACCT_BATT] == 3 && p[5 + ACCT_UNACCOUNTED] == 1,
          "ring 0: pass %u disp %u batt %u unacc %u", p[4], p[5 + ACCT_DISP_HK], p[5 + ACCT_BATT],
          p[5 + ACCT_UNACCOUNTED]);
    loop_acct_fill(17, p);
    CHECK(p[4] == 20 && p[5 + ACCT_UNACCOUNTED] == 20, "ring 1: all unaccounted: %u %u", p[4],
          p[5 + ACCT_UNACCOUNTED]);
    for (uint8_t pg = 0; pg <= 5; pg++) dump("ACCT", pg, loop_acct_fill);
    for (uint8_t pg = 16; pg < 19; pg++) dump("ACCT", pg, loop_acct_fill);

    /* Off: nothing accumulates, and nothing is left over for the next pass. */
    loop_acct_set_enabled(false);
    spend(ACCT_ANIM, 5000); pass(30);
    loop_acct_set_enabled(true);
    pass(3);
    loop_acct_fill(0, p);
    passes = p[4] | p[5] << 8 | p[6] << 16 | (uint32_t)p[7] << 24;
    CHECK(passes == 105, "a disabled pass is not counted: %u", passes);
    loop_acct_fill(4, p);   /* scopes 7-12: anim is 10 -> offset (10-7)*4 */
    CHECK(p[12] == 0 && p[13] == 0, "no anim time leaked across the off period");
}

#define KB 37u
static void write(uint32_t addr, const uint8_t *b, size_t len, int programs, bool erase) {
    eeprom_wear_leveling_write_hook(addr, b, len);
    bool changed = memcmp(&eeprom[addr], b, len) != 0;   /* wear_leveling_write skips an unchanged block */
    memcpy(&eeprom[addr], b, len);
    if (!changed) return;
    flash_stats_session();
    for (int i = 0; i < programs; i++) flash_stats_op(false);
    if (erase) flash_stats_op(true);
}

static void flash(void) {
    uint8_t blk[6] = {0x31, 0x40, 0x82, 10, 1, 101};
    write(KB, blk, 6, 2, false);                       /* first write: every field (mixed) */
    blk[1] = 0x80;                                     /* the RTC period alone, x5 */
    for (int i = 0; i < 5; i++) { blk[1]++; write(KB, blk, 6, 1, false); }
    blk[5] = 100; write(KB, blk, 6, 1, false);         /* the battery level alone */
    write(KB, blk, 6, 1, false);                       /* unchanged: no session */
    uint8_t rgb[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    write(23, rgb, 8, 3, true);                        /* RGB, with a consolidation erase */
    uint8_t via[2] = {0x12, 0x34};
    write(500, via, 2, 1, false);                      /* VIA's dynamic keymap */
    uint8_t same[6]; memcpy(same, &eeprom[KB], 6);
    eeprom_wear_leveling_write_hook(KB, same, 6);     /* an unchanged kb write: no session... */
    flash_stats_pass();                                /* ...and the pass ends */
    flash_stats_session(); flash_stats_op(false);      /* a session with no EEPROM write: other */
    flash_stats_rtc_proposal(33216, FLASH_RTC_PATH_SOF, false);
    flash_stats_rtc_proposal(33300, FLASH_RTC_PATH_PCF, true);

    uint8_t p[28];
    flash_stats_fill(0, p);
    uint32_t s_other = p[0], s_kb = p[4], s_rgb = p[8], s_via = p[12];
    CHECK(s_kb == 7 && s_rgb == 1 && s_via == 1 && s_other == 1, "sessions o%u kb%u rgb%u via%u", s_other, s_kb,
          s_rgb, s_via);
    CHECK(p[16 + 2 * FW_RGB] == 1, "the RGB session's erase");
    CHECK(p[24] == 1 && p[26] == 0, "kb mixed %u unknown %u", p[24], p[26]);
    flash_stats_fill(1, p);
    CHECK(p[16 + 2 * 1] == 5 && p[16 + 2 * 4] == 1, "rtc-alone %u batt-alone %u", p[18], p[24]);
    for (uint8_t pg = 0; pg <= 2; pg++) dump("FLASHW", pg, flash_stats_fill);
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    if (!strcmp(argv[1], "acct")) acct();
    else if (!strcmp(argv[1], "flash")) flash();
    else return 2;
    printf("%s %s\n", failures ? "FAIL" : "ok  ", argv[1]);
    return failures ? 1 : 0;
}
