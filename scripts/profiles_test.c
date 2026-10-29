/* Host test for keyboards/a_jazz/ak820pro/menu/profiles.c, the settings
 * profiles' store and HC_PROFILES (P5a, plans/SETTINGS-PROFILES-PLAN.md), and
 * what P5b adds: the deferred active slot, names, the `*`, the keys' step;
 * since 10-28 the menu's face on the live record.
 * Build and run, mingw64's gcc first on PATH:
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro
 *   gcc -std=c11 -Wall -Wextra -DMENU_HOST_TEST -I $D/menu scripts/profiles_test.c $D/menu/profiles.c -o pt && ./pt */
#include <stdio.h>
#include <string.h>

#include "menu_edit.h"
#include "menu_env.h"
#include "profiles.h"

void prof_test_reset(void);   /* profiles.c, MENU_HOST_TEST only: the reboot */

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* --- The fakes ------------------------------------------------------------------ */

/* The EEPROM: its cache, the writes in order, and a failure to inject. */
static uint8_t  ee[1024];
typedef struct { uint16_t addr; uint8_t n; uint8_t first; } wlog_t;
static wlog_t   wlog[64];
static int      nlog, fail_at = -1, consolidate_at = -1;
void env_prof_read(uint16_t addr, void *dst, uint8_t n) { memcpy(dst, &ee[addr], n); }
/* As the real layer does (wear_leveling.c): the cache is updated BEFORE the
 * flash is programmed, so a failed write leaves the new bytes in the cache. */
uint8_t env_prof_write(uint16_t addr, const void *src, uint8_t n) {
    int i = nlog;
    if (nlog < 64) wlog[nlog] = (wlog_t){addr, n, *(const uint8_t *)src};
    nlog++;
    memcpy(&ee[addr], src, n);
    if (i == fail_at) return ENV_WR_FAILED;
    return i == consolidate_at ? ENV_WR_CONSOLIDATED : ENV_WR_OK;
}
static bool fk_recovering;
bool        env_recovering(void) { return fk_recovering; }
static int  fk_flushes, fk_touches;
static bool fk_pending;   /* kb_eeconfig's write still to come */
static uint8_t fk_flush_last;   /* the last record's state when the flush ran (codex, 10-27: the order) */
void        env_settings_flush(void) {
    fk_flushes++;
    fk_pending    = false;
    fk_flush_last = ee[PROF_BASE + PROF_REC_OFF(PROF_LAST)];
}
void        env_settings_touch(void) { fk_touches++; fk_pending = true; }
bool        env_settings_pending(void) { return fk_pending; }

/* The live settings, and the setters' calls in order. */
static env_rgb_t fk_rgb = {2, 240, 215, 86, 127, 1, 0xFF};
static uint8_t   fk_lcd = 52, fk_ind[2] = {30, 60}, fk_clock = 4, fk_power = 1;
static uint8_t   fk_view = 1;   /* the battery readout, BATT_VIEW_* */
static char      calls[256];
static void      call(const char *s) { strncat(calls, s, sizeof calls - strlen(calls) - 1); }
void env_rgb_get(env_rgb_t *c) { *c = fk_rgb; }
void env_rgb_mode(uint8_t m, bool save) {
    if (fk_rgb.enable) fk_rgb.mode = m < 1 ? 1 : m;   /* QMK's: early return while off; mode 0 clamped to 1 */
    call(save ? "M" : "m");
}
void env_rgb_hsv(uint8_t h, uint8_t s, uint8_t v, bool save) {
    if (fk_rgb.enable) { fk_rgb.h = h; fk_rgb.s = s; fk_rgb.v = v; }
    call(save ? "H" : "h");
}
void env_rgb_speed(uint8_t sp, bool save) { fk_rgb.speed = sp; call(save ? "S" : "s"); }
void env_rgb_enable(bool on, bool save) { fk_rgb.enable = on; call(on ? (save ? "E" : "e") : (save ? "D" : "d")); }
uint8_t env_lcd_level(void) { return fk_lcd; }
void    env_lcd_set(uint8_t l, bool save) { fk_lcd = l; (void)save; call("L"); }
uint8_t env_ind_level(uint8_t w) { return fk_ind[w]; }
void    env_ind_set(uint8_t w, uint8_t l, bool save) { fk_ind[w] = l; (void)save; call("I"); }
uint8_t env_clock_mode(void) { return fk_clock; }
void    env_clock_set(uint8_t m) { fk_clock = m; call("C"); }
uint8_t env_batt_view(void) { return fk_view; }
void    env_batt_view_set(uint8_t v) { fk_view = v; call("B"); }
uint8_t env_power_mode(void) { return fk_power; }
void    env_power_set(uint8_t m) { fk_power = m; call("P"); }
/* 10-28, the menu's face: its own field here, as kb_eeconfig's setters keep
 * each other's, so a readout set never moves it; menu.c's menu_font_set(),
 * the one way to change it, counted. */
static uint8_t fk_font = ENV_FONT_LARGE;
static int     fk_font_sets;
uint8_t env_font(void) { return fk_font; }
void    env_font_set(uint8_t f) { fk_font = f; }
void    menu_font_set(uint8_t f) { fk_font_sets++; env_font_set(f); call("F"); }
/* The effects: modes 1, 2, 4 with stable ids 1, 2, 4 (a build with Breathing,
 * id 3, disabled). */
static const uint8_t fx_mode[3] = {1, 2, 3}, fx_id[3] = {1, 2, 4};
uint8_t env_effects(void) { return 3; }
uint8_t env_effect_mode(uint8_t i) { return i < 3 ? fx_mode[i] : 0; }
uint8_t env_effect_id(uint8_t i) { return i < 3 ? fx_id[i] : 0xFF; }
/* An open preview's rollback, by domain. */
static int fk_external[5];
static int fk_prev_lcd = -1;   /* an open preview's screen level to go back to (codex, 10-27), -1 none */
void       menu_edit_external(uint8_t d) {
    if (d < 5) fk_external[d]++;
    if (d == ME_DOM_LCD && fk_prev_lcd >= 0) {
        fk_lcd      = (uint8_t)fk_prev_lcd;
        fk_prev_lcd = -1;
    }
}
/* A flip's load, named (10-27). */
static int     fk_switched;
static uint8_t fk_sw_slot, fk_sw_st;
void           env_prof_switched(uint8_t slot, uint8_t st) { fk_switched++; fk_sw_slot = slot; fk_sw_st = st; }
/* Reset settings' defaults (10-27): JD's, as menu_glue.c reads them; mode 1
 * is Solid here (id 1). */
void env_defaults(env_defaults_t *d) {
    *d = (env_defaults_t){{1, 36, 64, 191, 102, 1, 0xFF}, 80, 5, 5, 0, 1, 1};   /* config.h's screen level: 80 (10-28) */
}

/* --- Helpers -------------------------------------------------------------------- */

static void reset(void) {
    memset(ee, 0, sizeof ee);
    nlog = 0; fail_at = consolidate_at = -1;
    fk_recovering = false;
    fk_pending = false; fk_touches = 0;
    fk_rgb = (env_rgb_t){2, 240, 215, 86, 127, 1, 0xFF};
    fk_lcd = 52; fk_ind[0] = 30; fk_ind[1] = 60; fk_clock = 4; fk_power = 1; fk_view = 1;
    fk_font = ENV_FONT_LARGE; fk_font_sets = 0;
    calls[0] = '\0';
    memset(fk_external, 0, sizeof fk_external);
    fk_switched = 0; fk_sw_slot = fk_sw_st = 0xEE;
    prof_test_reset();
}
#define B(off) ee[PROF_BASE + (off)]
/* kb_eeconfig's settled write done, then the 10 Hz tick: the pending active slot's write. */
static void settle(void) {
    fk_pending = false;
    prof_tick();
}
static uint8_t rpt[32];
static uint8_t hid(uint8_t sub, uint8_t a4, uint8_t a5) {
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = sub; rpt[4] = a4; rpt[5] = a5;
    return prof_hid(rpt) ? 1 : 0;
}

/* --- The tests ------------------------------------------------------------------ */

static void test_codec(void) {
    /* CRC-8 0x07, initial 0xFF: "123456789" is 0xFB. */
    CHECK(prof_crc8((const uint8_t *)"123456789", 9) == 0xFB);
    /* P5b's table against a bit at a time: every entry (a byte from the
     * initial 0xFF reaches each index once), then pseudo-random strings. */
    for (int b = 0; b < 256; b++) {
        uint8_t x = (uint8_t)b, c = (uint8_t)(0xFFu ^ x);
        for (int i = 0; i < 8; i++) c = (uint8_t)((c & 0x80u) ? (unsigned)(c << 1) ^ 0x07u : (unsigned)(c << 1));
        CHECK(prof_crc8(&x, 1) == c);
    }
    uint32_t seed = 7u;
    for (int k = 0; k < 200; k++) {
        uint8_t buf[40], n = (uint8_t)(k % 40), c = 0xFFu;
        for (int i = 0; i < n; i++) {
            seed   = seed * 1103515245u + 12345u;
            buf[i] = (uint8_t)(seed >> 16);
            c ^= buf[i];
            for (int j = 0; j < 8; j++) c = (uint8_t)((c & 0x80u) ? (unsigned)(c << 1) ^ 0x07u : (unsigned)(c << 1));
        }
        CHECK(prof_crc8(buf, n) == c);
    }
    reset();
    uint8_t r[PROF_REC];
    prof_capture(r, PF_PROFILE);
    CHECK(r[PR_STATE] == PS_SAVED_V1 && r[PR_FIELDS] == PF_PROFILE && r[PR_EFFECT] == 2 && r[PR_HUE] == 240 &&
          r[PR_LCD] == 52 && r[PR_LOCKS] == 30 && r[PR_CHARGING] == 60 && r[PR_CLOCK] == 4 && r[PR_BVIEW] == 1 &&
          r[PR_POWER] == 0 && prof_rec_valid(r));
    /* The crc leaves out the state: the state's three readings. */
    r[PR_STATE] = PS_EMPTY;  CHECK(!prof_rec_valid(r));
    r[PR_STATE] = 0x02;      CHECK(!prof_rec_valid(r));
    r[PR_STATE] = PS_SAVED_V1; CHECK(prof_rec_valid(r));
    r[PR_HUE]++;             CHECK(!prof_rec_valid(r));   /* damaged */
    r[PR_HUE]--;
    /* Ranges, each with its crc made good. */
    static const struct { uint8_t at, v; } bad[] = {
        {PR_RGB_ON, 2}, {PR_LCD, 101}, {PR_LOCKS, 101}, {PR_CHARGING, 101}, {PR_CLOCK, 6}, {PR_BVIEW, 0}, {PR_BVIEW, 4},
        {PR_NAME, 0x7F}, {PR_NAME, 0x1F},
    };
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        uint8_t q[PROF_REC];
        memcpy(q, r, PROF_REC);
        q[bad[i].at] = bad[i].v;
        q[PR_CRC]    = prof_crc8(&q[PR_FIELDS], PR_CRC - PR_FIELDS);
        CHECK(!prof_rec_valid(q));
    }
    uint8_t q[PROF_REC];
    memcpy(q, r, PROF_REC);
    memcpy(&q[PR_NAME], "Wo\0k", 4);   /* a character after the NUL */
    q[PR_CRC] = prof_crc8(&q[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(!prof_rec_valid(q));
    memcpy(&q[PR_NAME], "Work\0\0\0\0", 8);
    q[PR_CRC] = prof_crc8(&q[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(prof_rec_valid(q));
    /* The live record: the power mode, no name; a power mode out of range. */
    prof_capture(r, PF_LIVE);
    CHECK(r[PR_FIELDS] == 0xBF && r[PR_POWER] == 1 && prof_rec_valid(r));
    r[PR_POWER] = 4;
    r[PR_CRC]   = prof_crc8(&r[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(!prof_rec_valid(r));
}

static void test_format_and_save(void) {
    reset();
    /* A stale record from before the flash, at slot 2, and a stale active byte: unformatted, so nothing shows. */
    uint8_t r[PROF_REC];
    prof_capture(r, PF_PROFILE);
    memcpy(&ee[PROF_BASE + PROF_REC_OFF(2)], r, PROF_REC);
    B(PROF_OFF_ACTIVE) = 2;
    CHECK(!prof_formatted() && prof_active() == 0xFF && !prof_slot(2, r));
    /* The first save formats first: eight states (P5d), the active byte, the magic last; then the save. */
    bool c = true;
    CHECK(prof_free_slot() == 0 && prof_valid_mask() == 0);
    CHECK(prof_save(0, &c) == PROF_OK && !c);
    CHECK(nlog == 10 + 3);
    for (int s = 0; s < 8; s++) CHECK(wlog[s].addr == PROF_BASE + PROF_REC_OFF(s) && wlog[s].first == PS_EMPTY);
    CHECK(wlog[8].addr == PROF_BASE + PROF_OFF_ACTIVE && wlog[8].first == 0xFF);
    CHECK(wlog[9].addr == PROF_BASE + PROF_OFF_MAGIC && wlog[9].first == PROF_MAGIC_V4);
    /* The save: the state empty, the body (26 B), the state saved; the active
     * slot deferred (P5b): it counts at once, and is written only after
     * kb_eeconfig's settled write. */
    CHECK(wlog[10].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[10].first == PS_EMPTY && wlog[10].n == 1);
    CHECK(wlog[11].addr == PROF_BASE + PROF_REC_OFF(0) + 1 && wlog[11].n == 26);
    CHECK(wlog[12].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[12].first == PS_SAVED_V1 && wlog[12].n == 1);
    CHECK(B(PROF_OFF_ACTIVE) == 0xFF && prof_active() == 0 && fk_touches == 1 && fk_pending);
    prof_tick();
    CHECK(nlog == 13);   /* kb_eeconfig's write still to come */
    settle();
    CHECK(nlog == 14 && wlog[13].addr == PROF_BASE + PROF_OFF_ACTIVE && wlog[13].first == 0xF0 && wlog[13].n == 1);   /* Windows's, the Mac none (10-27) */
    settle();
    CHECK(nlog == 14);   /* once */
    CHECK(prof_valid_mask() == 0x01 && prof_free_slot() == 1);
    CHECK(prof_formatted() && prof_active() == 0 && prof_slot(0, r) && !prof_slot(2, r));
    /* A consolidation is reported. */
    nlog = 0; consolidate_at = 1;
    fk_rgb.h = 10;
    CHECK(prof_save(1, &c) == PROF_OK && c && prof_active() == 1);
    /* The name survives a save over the slot. */
    memcpy(&ee[PROF_BASE + PROF_REC_OFF(1) + PR_NAME], "Work", 4);
    uint8_t *rec1 = &ee[PROF_BASE + PROF_REC_OFF(1)];
    rec1[PR_CRC]  = prof_crc8(&rec1[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(prof_slot(1, r));
    fk_rgb.h = 20;
    CHECK(prof_save(1, NULL) == PROF_OK && prof_slot(1, r) && memcmp(&r[PR_NAME], "Work", 5) == 0 && r[PR_HUE] == 20);
    /* A write that fails mid-save: the slot reads empty (its state was written
     * empty first), though the cache holds the body. A retry of the same
     * settings is refused, not skipped as unchanged and committed (codex), and
     * so is every other profile write until a reboot. */
    nlog = 0; fail_at = 1;   /* the body's write */
    CHECK(prof_save(3, NULL) == PROF_WRITE_FAILED && !prof_slot(3, r) && prof_active() == 1 && prof_write_failed());
    fail_at = -1;
    nlog    = 0;
    CHECK(prof_save(3, NULL) == PROF_WRITE_FAILED && nlog == 0 && !prof_slot(3, r));
    calls[0] = '\0';
    CHECK(prof_delete(1) == PROF_WRITE_FAILED && prof_load(1) == PROF_WRITE_FAILED && nlog == 0);
    CHECK(calls[0] == '\0');   /* a refused load applies nothing */
    CHECK(hid(1, 0, 0x33) && rpt[6] == PROF_WRITE_FAILED && !prof_restore_open());
    CHECK(hid(0x40, 0, 0) && rpt[5] == PROF_WRITE_FAILED);
    prof_test_reset();   /* the reboot */
    /* A failed formatting (the magic, last): the latch, and the next write refused. */
    memset(&ee[PROF_BASE], 0, PROF_BLOCK_SIZE);
    nlog = 0; fail_at = 9;
    CHECK(prof_save(0, NULL) == PROF_WRITE_FAILED && prof_write_failed());
    fail_at = -1;
    CHECK(prof_save(0, NULL) == PROF_WRITE_FAILED && nlog == 10);
    prof_test_reset();
    memset(&ee[PROF_BASE], 0, PROF_BLOCK_SIZE);
    CHECK(prof_save(0, NULL) == PROF_OK && prof_save(1, NULL) == PROF_OK && prof_active() == 1);
    /* Busy: in a recovery, and with a restore open. */
    fk_recovering = true;
    CHECK(prof_save(2, NULL) == PROF_BUSY && prof_delete(1) == PROF_BUSY && prof_load(1) == PROF_BUSY);
    fk_recovering = false;
    CHECK(hid(1, 0, 0x5A) && rpt[6] == PROF_OK);
    CHECK(prof_save(2, NULL) == PROF_BUSY && prof_restore_open());
    for (int i = 0; i < 50; i++) prof_tick();
    CHECK(!prof_restore_open());
    CHECK(prof_save(2, NULL) == PROF_OK);   /* formats again: the Begin cleared the magic */
    CHECK(prof_save(8, NULL) == PROF_BAD && prof_save(9, NULL) == PROF_BAD);
    /* 10-27: seven profiles, the eighth record the last: no save, rename,
     * delete or load there. The seventh, and the free one the first without
     * a valid record. */
    CHECK(prof_save(7, NULL) == PROF_BAD && prof_rename(7, "x") == PROF_BAD && prof_delete(7) == PROF_BAD &&
          prof_load(7) == PROF_INVALID && !prof_slot(7, r));
    CHECK(prof_save(6, NULL) == PROF_OK && prof_valid_mask() == 0x44 && prof_free_slot() == 0);
    for (uint8_t s = 0; s < 7; s++) CHECK(prof_save(s, NULL) == PROF_OK);
    CHECK(prof_valid_mask() == 0x7F && prof_free_slot() == 0xFF && prof_active() == 6);
    CHECK(prof_delete(5) == PROF_OK && prof_free_slot() == 5 && prof_valid_mask() == 0x5F);
    B(PROF_OFF_MAGIC) = 0;   /* unformatted: nothing valid, slot 0 free */
    CHECK(prof_valid_mask() == 0 && prof_free_slot() == 0);
}

static void test_delete_and_load(void) {
    reset();
    uint8_t r[PROF_REC];
    fk_rgb.h = 100;
    CHECK(prof_save(0, NULL) == PROF_OK);
    fk_rgb.h = 200; fk_lcd = 10; fk_clock = 1; fk_view = 3;
    CHECK(prof_save(1, NULL) == PROF_OK && prof_active() == 1);
    /* Delete: the state alone (its crc still good), and the active slot to
     * none, deferred, if it was active. */
    nlog = 0;
    CHECK(prof_delete(1) == PROF_OK && nlog == 1 && !prof_slot(1, r) && prof_active() == 0xFF);
    CHECK(prof_delete(0) == PROF_OK && nlog == 2 && prof_active() == 0xFF);
    settle();
    CHECK(nlog == 3 && B(PROF_OFF_ACTIVE) == 0xFF);
    /* The active byte pointing at an empty slot reads as none. */
    CHECK(prof_save(0, NULL) == PROF_OK && prof_active() == 0);
    B(PROF_REC_OFF(0)) = 0x07;
    CHECK(prof_active() == 0xFF);
    B(PROF_REC_OFF(0)) = PS_SAVED_V1;
    /* Load, with the lights off: on unsaved first, then the mode, HSV, speed, the enable last at the record's value. */
    CHECK(prof_save(2, NULL) == PROF_OK);   /* h 200, lcd 10, clock 1, both (JD, 10-26) */
    fk_rgb.enable = 0; fk_rgb.h = 5; fk_lcd = 90; fk_clock = 0; fk_view = 1; fk_power = 3;
    calls[0] = '\0';
    CHECK(prof_load(2) == PROF_OK);
    CHECK(strcmp(calls, "eMHSELIICBF") == 0 && fk_rgb.enable == 1 && fk_rgb.h == 200 && fk_lcd == 10 && fk_clock == 1 &&
          fk_view == 3 && fk_power == 3 && prof_active() == 2);
    /* A record saved off stays off: the enable last, saved, at its value. */
    fk_rgb.enable = 0;
    CHECK(prof_save(3, NULL) == PROF_OK);
    fk_rgb.enable = 1;
    calls[0] = '\0';
    CHECK(prof_load(3) == PROF_OK && fk_rgb.enable == 0 && strcmp(calls, "eMHSDLIICBF") == 0);
    /* An effect id this build lacks (Breathing, 3): skipped, the rest loads. */
    uint8_t *rec = &ee[PROF_BASE + PROF_REC_OFF(2)];
    rec[PR_EFFECT] = 3;
    rec[PR_CRC]    = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    fk_rgb.mode = 1; fk_rgb.h = 0;
    calls[0] = '\0';
    CHECK(prof_load(2) == PROF_OK_EFFECT_SKIPPED && fk_rgb.mode == 1 && fk_rgb.h == 200 && strcmp(calls, "eHSELIICBF") == 0);
    /* Id 4 is mode 3 in this build. Id 0 is never assigned: QMK clamps mode 0
     * to 1, so a record holding it loads without its effect (codex). */
    rec[PR_EFFECT] = 4;
    rec[PR_CRC]    = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(prof_load(2) == PROF_OK && fk_rgb.mode == 3);
    rec[PR_EFFECT] = 0;
    rec[PR_CRC]    = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(prof_load(2) == PROF_OK_EFFECT_SKIPPED && fk_rgb.mode == 3);
    rec[PR_EFFECT] = 4;
    rec[PR_CRC]    = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    CHECK(prof_load(1) == PROF_INVALID);
    /* A stored record that carries the power mode (a restored one, say): a
     * load never applies it (Decided 2); only the live record's apply does. */
    rec[PR_FIELDS] |= PF_POWER;
    rec[PR_POWER] = 0;
    rec[PR_CRC]   = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    fk_power      = 3;
    CHECK(prof_load(2) == PROF_OK && fk_power == 3);
}

/* A whole restore over HC_PROFILES from a block image. */
/* 10-27: a last record for side sd, the live settings at hue h, straight
 * into the block (the eighth record, across the last two pages). */
static void put_last(uint8_t sd, uint8_t h) {
    uint8_t r[PROF_REC], h0 = fk_rgb.h;
    fk_rgb.h = h;
    prof_capture(r, PF_SIDE);
    fk_rgb.h = h0;
    r[PR_STATE] = (uint8_t)(PS_LAST | sd);   /* the crc leaves the state out */
    memcpy(&ee[PROF_BASE + PROF_REC_OFF(PROF_LAST)], r, PROF_REC);
}
static void make_image(uint8_t *img) {
    reset();
    fk_rgb.h = 11;
    prof_save(0, NULL);
    fk_rgb.h = 77;
    prof_save(6, NULL);   /* 10-27: the seventh, the last profile */
    fk_rgb.h = 22;
    prof_save(3, NULL);
    settle();
    put_last(PROF_SIDE_MAC, 99);   /* and the last record, the Mac's */
    memcpy(img, &ee[PROF_BASE], PROF_BLOCK_SIZE);
}
static void send_pages(const uint8_t *img, uint8_t token, uint8_t skip_page) {
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        if (p == skip_page) continue;
        hid(2, p, token);
        uint8_t n = (uint8_t)(PROF_BLOCK_SIZE - p * PROF_PAGE < PROF_PAGE ? PROF_BLOCK_SIZE - p * PROF_PAGE : PROF_PAGE);
        memcpy(&rpt[6], &img[p * PROF_PAGE], n);
        if (p == 0) rpt[6] = 0x55;   /* the host's magic: ignored */
        CHECK(prof_hid(rpt) && rpt[6] == (p > skip_page ? PROF_BAD : PROF_OK));   /* P5d: in order, so not past a gap */
    }
}

static void test_hid_restore(void) {
    uint8_t img[PROF_BLOCK_SIZE], r[PROF_REC];
    make_image(img);
    /* Read: nine pages of 26 B (P5d), zero past the end. */
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        CHECK(hid(0, p, 0) && rpt[5] == PROF_OK);
        uint8_t n = (uint8_t)(p < 8 ? 26 : 10);
        CHECK(memcmp(&rpt[6], &img[p * 26], n) == 0);
        if (p == 8) for (int i = 6 + 10; i < 32; i++) CHECK(rpt[i] == 0);
    }
    CHECK(hid(0, 9, 0) && rpt[5] == PROF_BAD);
    /* P5d: 7, the geometry. */
    CHECK(hid(7, 0, 0) && rpt[4] == 8 && rpt[5] == 27 && rpt[6] == 9 && rpt[7] == 26 && rpt[8] == 0xA4 && rpt[9] == 0);
    /* P5b: a pending choice reads as the board will write it, so a backup
     * taken inside the settle has it. */
    CHECK(prof_load(0) == PROF_OK && B(PROF_OFF_ACTIVE) == 0xF3);
    CHECK(hid(0, 0, 0) && rpt[6 + PROF_OFF_ACTIVE] == 0xF0 && rpt[6] == PROF_MAGIC_V4);
    /* A Begin drops it: the restore's active byte wins, not a choice
     * written after the commit. */
    CHECK(hid(1, 0, 0x59) && rpt[6] == PROF_OK);
    send_pages(img, 0x59, 0xFF);
    CHECK(hid(3, 0, 0x59) && rpt[6] == PROF_OK);
    settle();
    CHECK(!prof_restore_open() && B(PROF_OFF_ACTIVE) == 0xF3 && prof_active() == 3);
    /* A good restore onto a wiped block. */
    memset(&ee[PROF_BASE], 0, PROF_BLOCK_SIZE);
    CHECK(hid(1, 0, 0x5A) && rpt[6] == PROF_OK && B(PROF_OFF_MAGIC) == 0);
    send_pages(img, 0x5A, 0xFF);
    CHECK(B(PROF_OFF_MAGIC) == 0);   /* the magic masked until the commit */
    nlog = 0;
    CHECK(hid(3, 0, 0x5A) && rpt[6] == PROF_OK && !prof_restore_open());
    CHECK(wlog[nlog - 1].addr == PROF_BASE + PROF_OFF_MAGIC && wlog[nlog - 1].first == PROF_MAGIC_V4);   /* the magic last */
    CHECK(memcmp(&ee[PROF_BASE], img, PROF_BLOCK_SIZE) == 0 && prof_active() == 3 && prof_slot(0, r) && r[PR_HUE] == 11);
    CHECK(prof_slot(6, r) && r[PR_HUE] == 77);   /* the seventh slot */
    CHECK(ee[PROF_BASE + PROF_REC_OFF(PROF_LAST)] == (PS_LAST | PROF_SIDE_MAC) &&
          ee[PROF_BASE + PROF_REC_OFF(PROF_LAST) + PR_HUE] == 99);   /* the last record, in the last two pages */
    /* P5d: the pages in order. One ahead of the count is refused; a page
     * again (a lost reply's retry) is taken, the count unmoved. */
    CHECK(hid(1, 0, 0x5C) && rpt[6] == PROF_OK);
    CHECK(hid(2, 1, 0x5C) && rpt[6] == PROF_BAD);
    CHECK(hid(2, 0, 0x5C) && rpt[6] == PROF_OK && hid(2, 0, 0x5C) && rpt[6] == PROF_OK);
    CHECK(hid(2, 2, 0x5C) && rpt[6] == PROF_BAD);
    CHECK(hid(3, 0, 0x5C) && rpt[6] == PROF_INCOMPLETE && !prof_formatted());
    CHECK(hid(1, 0, 0x5D) && rpt[6] == PROF_OK);
    send_pages(img, 0x5D, 0xFF);
    CHECK(hid(2, 3, 0x5D) && rpt[6] == PROF_OK);   /* after all nine: any page again */
    memcpy(&rpt[6], &img[3 * PROF_PAGE], PROF_PAGE);
    rpt[3] = 2; rpt[4] = 3; rpt[5] = 0x5D;
    CHECK(prof_hid(rpt) && rpt[6] == PROF_OK);
    CHECK(hid(3, 0, 0x5D) && rpt[6] == PROF_OK && memcmp(&ee[PROF_BASE], img, PROF_BLOCK_SIZE) == 0);
    /* A missing page: refused, the block unformatted. */
    CHECK(hid(1, 0, 0x5B) && rpt[6] == PROF_OK);
    send_pages(img, 0x5B, 2);
    CHECK(hid(3, 0, 0x5B) && rpt[6] == PROF_INCOMPLETE && !prof_formatted() && !prof_restore_open());
    CHECK(hid(1, 0, 0x5E) && rpt[6] == PROF_OK);   /* P5d: only the ninth missing */
    send_pages(img, 0x5E, 8);
    CHECK(hid(3, 0, 0x5E) && rpt[6] == PROF_INCOMPLETE && !prof_formatted() && !prof_restore_open());
    /* A page from another token; a commit with another token. */
    CHECK(hid(1, 0, 0x01) && rpt[6] == PROF_OK);
    CHECK(hid(2, 0, 0x02) && rpt[6] == PROF_TOKEN);
    CHECK(hid(3, 0, 0x02) && rpt[6] == PROF_TOKEN && prof_restore_open());
    /* A second Begin aborts the first: its pages don't count. */
    send_pages(img, 0x01, 0xFF);
    CHECK(hid(1, 0, 0x03) && rpt[6] == PROF_OK);
    CHECK(hid(3, 0, 0x03) && rpt[6] == PROF_INCOMPLETE && !prof_formatted());
    /* The 5 s timeout: 50 ticks without a page. */
    CHECK(hid(1, 0, 0x04) && rpt[6] == PROF_OK);
    send_pages(img, 0x04, 4);
    for (int i = 0; i < 49; i++) prof_tick();
    CHECK(prof_restore_open());
    prof_tick();
    CHECK(!prof_restore_open());
    CHECK(hid(2, 4, 0x04) && rpt[6] == PROF_TOKEN && hid(3, 0, 0x04) && rpt[6] == PROF_TOKEN && !prof_formatted());
    /* A bad crc in one record: the whole restore refused. */
    uint8_t bad[PROF_BLOCK_SIZE];
    memcpy(bad, img, sizeof bad);
    bad[PROF_REC_OFF(3) + PR_HUE] ^= 1;
    CHECK(hid(1, 0, 0x05) && rpt[6] == PROF_OK);
    send_pages(bad, 0x05, 0xFF);
    CHECK(hid(3, 0, 0x05) && rpt[6] == PROF_INVALID && !prof_formatted() && prof_active() == 0xFF);
    /* 10-27: the eighth record is the last record or empty: a damaged one, a
     * profile there, a name in it, refused; empty, taken. */
    static const struct { uint8_t at, v; bool crc; } lastbad[3] = {
        {PR_HUE, 98, false}, {PR_STATE, PS_SAVED_V1, true}, {PR_FIELDS, PF_SIDE | PF_NAME, true},
    };
    for (int i = 0; i < 3; i++) {
        uint8_t *lr = &bad[PROF_REC_OFF(PROF_LAST)];
        memcpy(bad, img, sizeof bad);
        lr[lastbad[i].at] = lastbad[i].v;
        if (lastbad[i].crc) lr[PR_CRC] = prof_crc8(&lr[PR_FIELDS], PR_CRC - PR_FIELDS);
        CHECK(hid(1, 0, 0x05) && rpt[6] == PROF_OK);
        send_pages(bad, 0x05, 0xFF);
        CHECK(hid(3, 0, 0x05) && rpt[6] == PROF_INVALID && !prof_formatted());
    }
    memcpy(bad, img, sizeof bad);
    bad[PROF_REC_OFF(PROF_LAST)] = PS_EMPTY;
    CHECK(hid(1, 0, 0x05) && rpt[6] == PROF_OK);
    send_pages(bad, 0x05, 0xFF);
    CHECK(hid(3, 0, 0x05) && rpt[6] == PROF_OK && prof_formatted());
    /* An active byte pointing at an empty slot: normalized to none at the
     * commit, each side's (10-27): slots 0, 3 and 6 are saved; a nibble past
     * the profiles (7, the last record's, and 8-E) is none too. */
    static const uint8_t norm_in[6]  = {0xF1, 0x1A, 0x03, 0x6E, 0x9C, 0x76},
                         norm_out[6] = {0xFF, 0xFF, 0x03, 0x6F, 0xFF, 0xF6};   /* 10-27: 7 is the last record, no profile */
    uint8_t norm[PROF_BLOCK_SIZE];
    memcpy(norm, img, sizeof norm);
    for (int i = 0; i < 6; i++) {
        norm[PROF_OFF_ACTIVE] = norm_in[i];
        CHECK(hid(1, 0, 0x06) && rpt[6] == PROF_OK);
        send_pages(norm, 0x06, 0xFF);
        CHECK(hid(3, 0, 0x06) && rpt[6] == PROF_OK && B(PROF_OFF_ACTIVE) == norm_out[i] && prof_formatted());
    }
    /* Busy in a recovery: Begin refused; a commit keeps the transaction for a retry. */
    fk_recovering = true;
    CHECK(hid(1, 0, 0x07) && rpt[6] == PROF_BUSY && !prof_restore_open());
    fk_recovering = false;
    CHECK(hid(1, 0, 0x07) && rpt[6] == PROF_OK);
    send_pages(img, 0x07, 0xFF);
    fk_recovering = true;
    CHECK(hid(3, 0, 0x07) && rpt[6] == PROF_BUSY && prof_restore_open());
    fk_recovering = false;
    CHECK(hid(3, 0, 0x07) && rpt[6] == PROF_OK);
    /* A failed page write aborts, and latches: a new Begin is refused. */
    CHECK(hid(1, 0, 0x08) && rpt[6] == PROF_OK);
    nlog = 0; fail_at = 0;
    CHECK(hid(2, 0, 0x08) && rpt[6] == PROF_WRITE_FAILED && !prof_restore_open());   /* page 0: in order */
    fail_at = -1;
    CHECK(hid(1, 0, 0x09) && rpt[6] == PROF_WRITE_FAILED && !prof_restore_open());
}

static void test_hid_live(void) {
    reset();
    /* 4: the live record, 27 B at [4..30], status at [31]; a preview cancelled first. */
    CHECK(hid(4, 0, 0) && rpt[31] == PROF_OK && prof_rec_valid(&rpt[4]) && rpt[4 + PR_FIELDS] == PF_LIVE &&
          rpt[4 + PR_POWER] == 1 && rpt[4 + PR_HUE] == 240);
    CHECK(fk_external[ME_DOM_RGB] == 1 && fk_external[ME_DOM_LCD] == 1 && fk_external[ME_DOM_IND] == 1);
    uint8_t live[PROF_REC];
    memcpy(live, &rpt[4], PROF_REC);
    /* 5: apply it elsewhere, the power mode included. */
    fk_rgb.h = 1; fk_power = 3; fk_lcd = 0;
    memset(rpt, 0, sizeof rpt);
    rpt[3] = 5;
    memcpy(&rpt[4], live, PROF_REC);
    CHECK(prof_hid(rpt) && rpt[31] == PROF_OK && fk_rgb.h == 240 && fk_power == 1 && fk_lcd == 52);
    CHECK(fk_external[ME_DOM_RGB] == 2);
    /* A bad record, an unknown format, a recovery: refused, nothing applied. */
    fk_power = 3;
    rpt[3] = 5;
    memcpy(&rpt[4], live, PROF_REC);
    rpt[4 + PR_POWER] = 1; rpt[4 + PR_HUE] ^= 1;
    CHECK(prof_hid(rpt) && rpt[31] == PROF_INVALID && fk_power == 3);
    rpt[3] = 5;
    memcpy(&rpt[4], live, PROF_REC);
    rpt[4 + PR_STATE] = 0x02;
    CHECK(prof_hid(rpt) && rpt[31] == PROF_FORMAT);
    fk_recovering = true;
    rpt[3] = 5;
    memcpy(&rpt[4], live, PROF_REC);
    CHECK(prof_hid(rpt) && rpt[31] == PROF_BUSY && fk_power == 3);
    /* 6: the flush, a preview cancelled first; busy in a recovery. */
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_BUSY && fk_flushes == 0);
    fk_recovering = false;
    int ext = fk_external[ME_DOM_RGB];
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_OK && fk_flushes == 1 && fk_external[ME_DOM_RGB] == ext + 1);
    /* An unknown sub: unhandled. Dev's 0x40 save and 0x41 delete. */
    CHECK(!hid(8, 0, 0) && !hid(0x43, 0, 0));
    CHECK(hid(0x40, 1, 0) && rpt[5] == PROF_OK && prof_active() == 1);
    CHECK(hid(0x41, 1, 0) && rpt[5] == PROF_OK && prof_active() == 0xFF);
    /* P5b: the flush writes the pending active slot too. */
    CHECK(hid(0x40, 2, 0) && rpt[5] == PROF_OK && B(PROF_OFF_ACTIVE) != 2 && prof_active() == 2);
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_OK && B(PROF_OFF_ACTIVE) == 0xF2);
    int n = nlog;
    settle();
    CHECK(nlog == n);   /* nothing left to write */
}

/* P5b: names, the `*`, the keys' step, the coalesced active slot, the menu's repaint flag. */
static void test_p5b(void) {
    reset();
    uint8_t r[PROF_REC], s = 9;
    char    nm[PROF_NAME + 1];
    /* Nothing saved: the keys load nothing, and touch nothing. */
    CHECK(prof_step(true, &s) == PROF_INVALID && prof_step(false, &s) == PROF_INVALID && s == 9);
    CHECK(calls[0] == 0 && fk_external[ME_DOM_RGB] == 0 && nlog == 0 && fk_touches == 0);
    /* Names: "Profile n" without one; the name, all 12, with one. */
    fk_rgb.h = 1;
    CHECK(prof_save(0, NULL) == PROF_OK);
    fk_rgb.h = 3;
    CHECK(prof_save(2, NULL) == PROF_OK);
    settle();
    CHECK(prof_slot(2, r));
    prof_name(2, r, nm);
    CHECK(strcmp(nm, "Profile 3") == 0);
    memcpy(&r[PR_NAME], "Twelve chars", 12);
    prof_name(2, r, nm);
    CHECK(strcmp(nm, "Twelve chars") == 0);
    r[PR_FIELDS] &= (uint8_t)~PF_NAME;
    prof_name(2, r, nm);
    CHECK(strcmp(nm, "Profile 3") == 0);
    prof_name(7, r, nm);
    CHECK(strcmp(nm, "Profile 8") == 0);   /* P5d */
    /* The `*`: a compare of the record's fields. */
    CHECK(prof_active_rec(r) == 2 && !prof_differs(r));
    fk_lcd = 53;   CHECK(prof_differs(r));
    fk_lcd = 52;   CHECK(!prof_differs(r));
    fk_power = 3;  CHECK(!prof_differs(r));   /* not a profile's (Decided 2) */
    fk_rgb.mode = 1; CHECK(prof_differs(r));
    fk_rgb.mode = 2; fk_rgb.speed = 1; CHECK(prof_differs(r));
    fk_rgb.speed = 127; fk_view = 2; CHECK(prof_differs(r));
    fk_view = 1; fk_ind[1] = 61; CHECK(prof_differs(r));
    r[PR_FIELDS] &= (uint8_t)~PF_CHARGING; CHECK(!prof_differs(r));   /* a field it doesn't hold */
    fk_ind[1] = 60; fk_clock = 0; CHECK(prof_differs(r));
    fk_clock = 4; fk_rgb.enable = 0; CHECK(prof_differs(r));
    fk_rgb.enable = 1;
    /* Next and Previous from slot 2, slots 0 and 2 saved: wrapping, skipping
     * empties; a preview cancelled first; the load applied. */
    calls[0] = 0;
    CHECK(prof_step(true, &s) == PROF_OK && s == 0 && fk_rgb.h == 1 && fk_external[ME_DOM_RGB] == 1 &&
          fk_external[ME_DOM_LCD] == 1 && fk_external[ME_DOM_IND] == 1 && calls[0] == 'e');
    CHECK(prof_step(true, &s) == PROF_OK && s == 2 && fk_rgb.h == 3);
    CHECK(prof_step(true, &s) == PROF_OK && s == 0);
    CHECK(prof_step(false, &s) == PROF_OK && s == 2);
    CHECK(prof_step(false, &s) == PROF_OK && s == 0 && prof_active() == 0);
    /* Four presses: one active-byte write, after kb_eeconfig's. */
    int n = nlog;
    for (int i = 0; i < 4; i++) CHECK(prof_step(true, &s) == PROF_OK);
    CHECK(s == 0 && nlog == n && prof_active() == 0);
    prof_tick();
    CHECK(nlog == n);
    settle();
    CHECK(nlog == n + 1 && wlog[n].addr == PROF_BASE + PROF_OFF_ACTIVE && wlog[n].first == 0xF0);
    /* Three saved, so the two directions differ: from slot 2, Next wraps to
     * 0, then Previous walks back 2, 1, 0. */
    CHECK(prof_save(1, NULL) == PROF_OK && prof_save(2, NULL) == PROF_OK && prof_active() == 2);
    CHECK(prof_step(true, &s) == PROF_OK && s == 0);
    CHECK(prof_step(false, &s) == PROF_OK && s == 2);
    CHECK(prof_step(false, &s) == PROF_OK && s == 1);
    CHECK(prof_step(false, &s) == PROF_OK && s == 0);
    CHECK(prof_step(true, &s) == PROF_OK && s == 1);
    /* From none, slots 0 and 2 saved: Previous the last, Next the first. */
    CHECK(prof_delete(1) == PROF_OK && prof_active() == 0xFF);
    CHECK(prof_step(false, &s) == PROF_OK && s == 2);
    CHECK(prof_save(1, NULL) == PROF_OK && prof_delete(1) == PROF_OK && prof_active() == 0xFF);
    CHECK(prof_step(true, &s) == PROF_OK && s == 0);
    /* Deleting another slot leaves the active one. */
    CHECK(prof_save(3, NULL) == PROF_OK && prof_step(true, &s) == PROF_OK && s == 0);
    CHECK(prof_delete(3) == PROF_OK && prof_active() == 0);
    /* From no active slot: Next the first saved, Previous the last. */
    CHECK(prof_delete(0) == PROF_OK && prof_active() == 0xFF);
    CHECK(prof_step(false, &s) == PROF_OK && s == 2);
    CHECK(prof_delete(2) == PROF_OK && prof_save(1, NULL) == PROF_OK && prof_save(3, NULL) == PROF_OK);
    CHECK(prof_delete(3) == PROF_OK && prof_active() == 0xFF);
    CHECK(prof_step(true, &s) == PROF_OK && s == 1);
    /* One saved slot: a press reloads it, clearing its `*`. */
    fk_lcd = 7;
    CHECK(prof_active_rec(r) == 1 && prof_differs(r));
    CHECK(prof_step(true, &s) == PROF_OK && s == 1 && fk_lcd == 52 && !prof_differs(r));
    CHECK(prof_step(false, &s) == PROF_OK && s == 1);
    /* Refused in a recovery and during a restore: nothing applied, nothing cancelled. */
    int ext = fk_external[ME_DOM_RGB];
    fk_recovering = true;
    fk_lcd = 7; calls[0] = 0;
    CHECK(prof_step(true, &s) == PROF_BUSY && fk_lcd == 7 && calls[0] == 0 && fk_external[ME_DOM_RGB] == ext);
    /* ... and the pending byte waits out the recovery. */
    CHECK(prof_delete(1) == PROF_BUSY);
    fk_recovering = false;
    CHECK(prof_load(1) == PROF_OK);
    n = nlog;
    fk_recovering = true;
    settle();
    CHECK(nlog == n);
    fk_recovering = false;
    settle();
    CHECK(nlog == n + 1);
    CHECK(!prof_take_changed());   /* the menu's own writes: no repaint flag */
    CHECK(hid(1, 0, 0x22) && rpt[6] == PROF_OK);
    fk_lcd = 7;
    CHECK(prof_step(true, &s) == PROF_BUSY && fk_lcd == 7);
    CHECK(prof_take_changed() && !prof_take_changed());   /* the host's Begin: a repaint, once */
    for (int i = 0; i < 50; i++) prof_tick();
    CHECK(!prof_restore_open() && !prof_formatted() && !prof_take_changed());
    /* A pending byte on a block the abort left unformatted: dropped, not written. */
    CHECK(prof_save(0, NULL) == PROF_OK && prof_formatted());
    B(PROF_OFF_MAGIC) = 0;
    n = nlog;
    settle();
    CHECK(nlog == n && prof_active() == 0xFF);
    /* The deferred byte's failure (codex, P5b's review): latched, so every
     * later profile write is refused, and the flush reports it, whether its
     * own write fails or the latch already holds the choice. */
    reset();
    CHECK(prof_save(0, NULL) == PROF_OK && prof_save(1, NULL) == PROF_OK);
    settle();
    CHECK(prof_load(0) == PROF_OK);
    fail_at = nlog;
    settle();
    CHECK(prof_write_failed() && prof_save(2, NULL) == PROF_WRITE_FAILED);
    /* Nothing pending now (the tick's write took it), and still the flush
     * says so, every time (codex's verify). */
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_WRITE_FAILED);
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_WRITE_FAILED);
    prof_test_reset();
    CHECK(prof_load(1) == PROF_OK);
    fail_at = nlog;
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_WRITE_FAILED && prof_write_failed());
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_WRITE_FAILED);   /* the repeat too */
    prof_test_reset();
    fail_at = -1;
    CHECK(prof_load(0) == PROF_OK);
    fail_at = nlog;
    CHECK(prof_save(2, NULL) == PROF_WRITE_FAILED);   /* the latch, the choice still pending */
    fail_at = -1;
    n = nlog;
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_WRITE_FAILED && nlog == n);
    prof_test_reset();
    CHECK(hid(6, 0, 0) && rpt[4] == PROF_OK);   /* nothing pending: the flush's own */
    CHECK(prof_save(0, NULL) == PROF_OK && prof_formatted());
    /* Every HC write sub sets it: a commit, the dev save and delete. */
    CHECK(hid(0x40, 0, 0) && prof_take_changed());
    CHECK(hid(0x41, 0, 0) && prof_take_changed());
    CHECK(hid(3, 0, 0x22) && rpt[6] == PROF_TOKEN && !prof_take_changed());   /* no restore open: nothing written */
}

/* P5c: Rename's write: the state empty, the name and the crc (the fields too
 * when they lacked the name bit), the state saved; the active slot kept. */
static void test_rename(void) {
    reset();
    uint8_t r[PROF_REC];
    CHECK(prof_save(0, NULL) == PROF_OK && prof_save(1, NULL) == PROF_OK);
    settle();
    nlog = 0;
    CHECK(prof_rename(0, "Home") == PROF_OK && nlog == 3);
    CHECK(wlog[0].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[0].first == PS_EMPTY && wlog[0].n == 1);
    CHECK(wlog[1].addr == PROF_BASE + PROF_REC_OFF(0) + PR_NAME && wlog[1].first == 'H' && wlog[1].n == 13);
    CHECK(wlog[2].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[2].first == PS_SAVED_V1 && wlog[2].n == 1);
    CHECK(prof_slot(0, r) && memcmp(&r[PR_NAME], "Home\0\0\0\0\0\0\0\0", 12) == 0 && prof_active() == 1);
    /* Twelve, then empty ("Profile n" again); the bit stays. */
    CHECK(prof_rename(0, "Twelve chars") == PROF_OK && prof_slot(0, r) && memcmp(&r[PR_NAME], "Twelve chars", 12) == 0);
    CHECK(prof_rename(0, "") == PROF_OK && prof_slot(0, r) && r[PR_NAME] == 0 && (r[PR_FIELDS] & PF_NAME));
    /* A record without the name bit (a host's): the fields written too. */
    uint8_t *rec = &ee[PROF_BASE + PROF_REC_OFF(1)];
    rec[PR_FIELDS] &= (uint8_t)~PF_NAME;
    rec[PR_CRC] = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    nlog = 0;
    CHECK(prof_rename(1, "Work") == PROF_OK && nlog == 3 && wlog[1].addr == PROF_BASE + PROF_REC_OFF(1) + PR_FIELDS &&
          wlog[1].n == 26);
    CHECK(prof_slot(1, r) && (r[PR_FIELDS] & PF_NAME) && memcmp(&r[PR_NAME], "Work", 5) == 0);
    /* Refused: no slot, an empty slot, a character outside 0x20-0x7E, a
     * recovery; nothing written. */
    nlog = 0;
    CHECK(prof_rename(8, "x") == PROF_BAD && prof_rename(5, "x") == PROF_INVALID && prof_rename(0, "a\x7f") == PROF_INVALID);
    fk_recovering = true;
    CHECK(prof_rename(0, "x") == PROF_BUSY);
    fk_recovering = false;
    CHECK(nlog == 0 && prof_slot(0, r) && r[PR_NAME] == 0);
    /* A failed write: the slot reads empty, and the latch refuses the rest. */
    fail_at = 1;
    CHECK(prof_rename(0, "Fail") == PROF_WRITE_FAILED && !prof_slot(0, r) && prof_write_failed());
    fail_at = -1;
    CHECK(prof_rename(1, "x") == PROF_WRITE_FAILED);
    prof_test_reset();
}

/* 10-27 (JD: "the current profile is remembered for windows and Mac
 * layers"; then "don't lose your settings when switching between
 * mac/windows"): each side of the Win/Mac switch remembers its slot in its
 * nibble of the active byte; a flip, once the switch has rested three
 * ticks, keeps the side left in the last record and brings the side arrived
 * at back as it was left, else loads its profile. Only a side with a
 * profile keeps its settings. */
static void ticks(int n) { for (int i = 0; i < n; i++) prof_tick(); }
static uint8_t pair_now(void) {   /* the active byte as the board will write it */
    hid(0, 0, 0);
    return rpt[6 + PROF_OFF_ACTIVE];
}
static uint8_t last_state(void) { return B(PROF_REC_OFF(PROF_LAST) + PR_STATE); }
static uint8_t last_lcd(void) { return B(PROF_REC_OFF(PROF_LAST) + PR_LCD); }
#define LAST_WIN (PS_LAST | PROF_SIDE_WIN)
#define LAST_MAC (PS_LAST | PROF_SIDE_MAC)
static void test_switch(void) {
    reset();
    uint8_t s = 9, r[PROF_REC];
    /* The boot's reading, the Mac's: nothing loaded, no countdown. */
    prof_switch(true);
    ticks(5);
    CHECK(calls[0] == 0 && fk_switched == 0 && hid(7, 0, 0) && rpt[9] == 2);
    /* Saved on the Mac: its nibble, Windows' none. */
    fk_rgb.h = 50; fk_lcd = 20;
    CHECK(prof_save(0, NULL) == PROF_OK && prof_active() == 0);
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0x0F);
    /* To Windows, which remembers none: the side the profiles go by moves
     * at the countdown's end; nothing loads; the Mac's settings kept. */
    prof_switch(false);
    calls[0] = 0;
    ticks(2);
    CHECK(prof_active() == 0 && hid(7, 0, 0) && rpt[9] == 2 && last_state() == PS_EMPTY);
    ticks(1);
    CHECK(prof_active() == 0xFF && hid(7, 0, 0) && rpt[9] == 1 && calls[0] == 0 && fk_switched == 0 && fk_lcd == 20);
    CHECK(last_state() == LAST_MAC && last_lcd() == 20);
    /* Saved on Windows: its nibble. */
    fk_rgb.h = 150; fk_lcd = 80;
    CHECK(prof_save(1, NULL) == PROF_OK && prof_active() == 1);
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0x01 && last_state() == LAST_MAC);
    /* To the Mac: its settings back at the third tick, a preview cancelled
     * first, named; Windows' kept; once. */
    int ext = fk_external[ME_DOM_RGB];
    prof_switch(true);
    ticks(2);
    CHECK(fk_switched == 0 && fk_lcd == 80);
    ticks(1);
    CHECK(fk_switched == 1 && fk_sw_slot == 0 && fk_sw_st == PROF_OK && fk_lcd == 20 && fk_rgb.h == 50 &&
          prof_active() == 0 && fk_external[ME_DOM_RGB] == ext + 1);
    CHECK(last_state() == LAST_WIN && last_lcd() == 80);
    ticks(10);
    CHECK(fk_switched == 1);
    /* A change on the Mac (its `*`) survives a flip there and back: JD's
     * "don't lose your settings". The pair never moves. */
    fk_lcd = 33;
    prof_switch(false);
    ticks(3);
    CHECK(fk_switched == 2 && fk_sw_slot == 1 && fk_lcd == 80 && prof_active() == 1 && last_lcd() == 33);
    prof_switch(true);
    ticks(3);
    CHECK(fk_switched == 3 && fk_sw_slot == 0 && fk_lcd == 33 && fk_rgb.h == 50 && prof_active_rec(r) == 0 &&
          prof_differs(r));
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0x01);
    /* A bounce back before the rest changes nothing. A contact bouncing on
     * its way over flips once, the rest counted from its last edge. */
    prof_switch(false); ticks(1); prof_switch(true); ticks(5);
    CHECK(fk_switched == 3 && fk_lcd == 33 && prof_active() == 0);
    prof_switch(false); prof_switch(true); prof_switch(false); ticks(2);
    prof_switch(true); ticks(1); prof_switch(false); ticks(2);
    CHECK(fk_switched == 3);
    ticks(1);
    CHECK(fk_switched == 4 && fk_sw_slot == 1 && fk_lcd == 80);
    /* A reading of the side it's on (a wake's, say): nothing, and in a
     * countdown, no restart. */
    prof_switch(false); ticks(5);
    CHECK(fk_switched == 4);
    prof_switch(true); ticks(2); prof_switch(true); ticks(1);
    CHECK(fk_switched == 5 && fk_lcd == 33);
    /* The flip waits out a recovery at the countdown's end, then goes. */
    prof_switch(false); ticks(2);
    fk_recovering = true;
    ticks(5);
    CHECK(fk_switched == 5 && prof_active() == 0 && fk_lcd == 33);
    fk_recovering = false;
    ticks(1);
    CHECK(fk_switched == 6 && fk_sw_slot == 1 && fk_lcd == 80 && last_state() == LAST_MAC && last_lcd() == 33);
    /* Save, the keys and Load record on the side the profiles go by. */
    fk_rgb.h = 99;
    CHECK(prof_save(2, NULL) == PROF_OK && pair_now() == 0x02);
    CHECK(prof_step(true, &s) == PROF_OK && s == 0 && pair_now() == 0x00);
    CHECK(prof_load(2) == PROF_OK && pair_now() == 0x02);
    /* ... and in a flip's countdown, on the side it was on. */
    prof_switch(true); ticks(1);
    CHECK(prof_save(1, NULL) == PROF_OK && pair_now() == 0x01);
    ticks(2);
    CHECK(fk_switched == 7 && fk_sw_slot == 0 && prof_active() == 0 && fk_lcd == 33 && last_state() == LAST_WIN);
    /* A profile saved again that the other side uses: that side's settings
     * as left would bring the old one back, so they go, and it loads anew. */
    fk_lcd = 61;
    CHECK(prof_save(1, NULL) == PROF_OK && pair_now() == 0x11 && last_state() == PS_EMPTY);
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 8 && fk_sw_slot == 1 && fk_lcd == 61 && last_state() == LAST_MAC);
    /* Delete: either side's slot, and that side's settings as left. Both on
     * slot 1, then none on both, the last record gone. */
    CHECK(prof_delete(1) == PROF_OK && pair_now() == 0xFF && prof_active() == 0xFF && last_state() == PS_EMPTY);
    /* A side without a profile keeps nothing of its own: it shows what was
     * there, and arriving back at the side with one brings that back. */
    CHECK(prof_load(0) == PROF_OK && pair_now() == 0xF0);
    fk_lcd = 70;
    prof_switch(true); ticks(3);
    CHECK(fk_switched == 8 && fk_lcd == 70 && last_state() == LAST_WIN && last_lcd() == 70);
    fk_lcd = 71;
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 9 && fk_sw_slot == 0 && fk_lcd == 70 && last_state() == PS_EMPTY);   /* used: no stale copy */
    prof_switch(true); ticks(3);
    CHECK(fk_switched == 9 && fk_lcd == 70);   /* the Mac's 71 not kept */
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 10 && fk_lcd == 70);
    /* The other side's slot deleted: its settings as left go too; this
     * side's slot kept. */
    prof_switch(true); ticks(3);
    CHECK(prof_load(2) == PROF_OK && pair_now() == 0x20);
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 11 && fk_sw_slot == 0 && last_state() == LAST_MAC);
    CHECK(prof_delete(2) == PROF_OK && pair_now() == 0xF0 && prof_active() == 0 && last_state() == PS_EMPTY);
    /* A flip refused by the latch: nothing applied or kept; the side moves. */
    fk_lcd = 77;
    prof_switch(true); ticks(3);
    CHECK(fk_switched == 11 && last_state() == LAST_WIN && last_lcd() == 77);
    CHECK(prof_save(3, NULL) == PROF_OK && pair_now() == 0x30);
    fk_lcd = 78;
    fail_at = nlog;
    settle();
    CHECK(prof_write_failed() && B(PROF_OFF_ACTIVE) == 0x30);
    fail_at = -1;
    calls[0] = 0;
    int n = nlog;
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 12 && fk_sw_slot == 0 && fk_sw_st == PROF_WRITE_FAILED && calls[0] == 0 && prof_active() == 0 &&
          nlog == n && fk_lcd == 78);
    /* The reboot on the Mac's side, the switch where it was: its slot,
     * nothing loaded (the last record is Windows'). */
    prof_test_reset();
    prof_switch(true);
    ticks(5);
    CHECK(fk_switched == 12 && prof_active() == 3 && hid(7, 0, 0) && rpt[9] == 2 && fk_lcd == 78);
    /* The switch moved while the board was off: the boot on Windows finds
     * Windows' settings in the last record, so the live ones are the Mac's.
     * At the first tick, the flip's swap. */
    prof_test_reset();
    prof_switch(false);
    CHECK(fk_switched == 12 && fk_lcd == 78);
    ticks(1);
    CHECK(fk_switched == 13 && fk_sw_slot == 0 && fk_lcd == 77 && prof_active() == 0 && hid(7, 0, 0) && rpt[9] == 1 &&
          last_state() == LAST_MAC && last_lcd() == 78);
    ticks(5);
    CHECK(fk_switched == 13);
    /* Dev's 0x42: the switch read as [4], as a flip. */
    CHECK(hid(0x42, 1, 0) && rpt[5] == PROF_OK);
    ticks(3);
    CHECK(fk_switched == 14 && fk_sw_slot == 3 && fk_sw_st == PROF_OK && fk_lcd == 78);
    CHECK(hid(0x42, 0, 0) && rpt[5] == PROF_OK);
    ticks(3);
    CHECK(fk_switched == 15 && fk_sw_slot == 0 && fk_lcd == 77);
    /* A flip while a restore is open waits for it; the abort leaves the block
     * unformatted, so nothing loads or is kept. */
    CHECK(hid(1, 0, 0x31) && rpt[6] == PROF_OK);
    prof_switch(true);
    ticks(49);
    CHECK(prof_restore_open() && fk_switched == 15 && hid(7, 0, 0) && rpt[9] == 1);
    n = nlog;
    ticks(1);
    CHECK(!prof_restore_open() && fk_switched == 15 && hid(7, 0, 0) && rpt[9] == 2 && nlog == n);
}

/* Codex's review (10-27): a flip keeps the side's own settings, not an open
 * preview's; the arrived side's settings are saved before the left side's
 * record is written; Reset is busy in a recovery even under the latch. */
static void test_switch_codex(void) {
    reset();
    prof_switch(false);
    ticks(1);
    fk_lcd = 20;
    CHECK(prof_save(0, NULL) == PROF_OK);
    prof_switch(true); ticks(3);   /* the Mac, none yet: Windows' kept */
    fk_lcd = 30;
    CHECK(prof_save(1, NULL) == PROF_OK);
    settle();
    fk_lcd = 31;                   /* the Mac's own, its `*` */
    fk_prev_lcd = 31; fk_lcd = 99; /* and a preview showing over it */
    int fl = fk_flushes;
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 1 && fk_sw_slot == 0 && fk_lcd == 20 && fk_prev_lcd == -1);
    CHECK(last_state() == LAST_MAC && last_lcd() == 31);   /* not the preview's 99 */
    CHECK(fk_flushes == fl + 1 && fk_flush_last == LAST_WIN);   /* saved while the record still held Windows' */
    /* A flip to a side without a profile applies nothing, so saves nothing early. */
    CHECK(prof_delete(1) == PROF_OK);
    fl = fk_flushes;
    prof_switch(true); ticks(3);
    CHECK(fk_flushes == fl && last_state() == LAST_WIN && fk_lcd == 20);
    /* Reset: busy in a recovery, the latch or not. */
    fail_at = nlog;
    CHECK(prof_save(2, NULL) == PROF_WRITE_FAILED && prof_write_failed());
    fail_at = -1;
    fk_recovering = true;
    calls[0] = '\0';
    CHECK(prof_reset() == PROF_BUSY && calls[0] == '\0' && fk_lcd == 20);
    fk_recovering = false;
    CHECK(prof_reset() == PROF_OK && fk_lcd == 80);   /* under the latch it still applies; nothing written */
    prof_test_reset();
}

/* 10-27: Reset settings. The defaults applied and saved, the power mode's
 * too; both sides forget their profile and the last record goes; the
 * profiles stay. */
static void test_reset(void) {
    reset();
    /* Never formatted: the defaults, nothing written. */
    prof_switch(false);
    ticks(1);
    int ext = fk_external[ME_DOM_RGB];
    calls[0] = '\0';
    CHECK(prof_reset() == PROF_OK && nlog == 0);
    CHECK(strcmp(calls, "eMHSELIICBFP") == 0 && fk_rgb.mode == 1 && fk_rgb.h == 36 && fk_rgb.s == 64 &&
          fk_rgb.v == 191 && fk_rgb.speed == 102 && fk_rgb.enable == 1 && fk_lcd == 80 && fk_ind[0] == 5 &&
          fk_ind[1] == 5 && fk_clock == 0 && fk_view == 1 && fk_power == 1 && fk_external[ME_DOM_RGB] == ext + 1);
    /* With a profile a side and the last record: those go, the profiles stay. */
    fk_lcd = 20;
    CHECK(prof_save(0, NULL) == PROF_OK);
    prof_switch(true); ticks(3);
    fk_lcd = 30;
    CHECK(prof_save(1, NULL) == PROF_OK);
    prof_switch(false); ticks(3);
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0x10 && last_state() == LAST_MAC && fk_lcd == 20 && fk_switched == 1);
    fk_power = 3;
    CHECK(prof_reset() == PROF_OK && fk_lcd == 80 && fk_power == 1 && pair_now() == 0xFF && last_state() == PS_EMPTY &&
          prof_active() == 0xFF && prof_valid_mask() == 0x03);
    settle();
    CHECK(B(PROF_OFF_ACTIVE) == 0xFF);
    /* A flip after it changes nothing: neither side has a profile. */
    prof_switch(true); ticks(3);
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 1 && fk_lcd == 80 && last_state() == PS_EMPTY);
    /* Busy in a recovery or a restore: nothing applied. */
    fk_lcd = 7;
    calls[0] = '\0';
    fk_recovering = true;
    CHECK(prof_reset() == PROF_BUSY && fk_lcd == 7 && calls[0] == '\0');
    fk_recovering = false;
    CHECK(hid(1, 0, 0x41) && rpt[6] == PROF_OK);
    CHECK(prof_reset() == PROF_BUSY && fk_lcd == 7);
    prof_test_reset();
}

/* 10-28, the Font setting (plans/MENU-8X16-PLAN.md B5), every record's since
 * JD's "make profiles respect the font size setting": the face in PR_BVIEW's
 * bits 2-3 beside the readout (bit 2 Small, bit 3 Regular, neither Large),
 * captured with it, compared for the `*`, range-checked, and applied through
 * menu_font_set(). A record from before has the bits clear: Large. Both
 * bits, or any above them, is out of range. */
static uint8_t apply5(const uint8_t *rec) {   /* HC_PROFILES 5 of rec: its status */
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 5;
    memcpy(&rpt[4], rec, PROF_REC);
    CHECK(prof_hid(rpt));
    return rpt[31];
}
static void recrc(uint8_t *r) { r[PR_CRC] = prof_crc8(&r[PR_FIELDS], PR_CRC - PR_FIELDS); }
static void test_font(void) {
    reset();
    uint8_t r[PROF_REC], q[PROF_REC], small[PROF_REC], large[PROF_REC], reg[PROF_REC], s = 9;
    /* Saved in Small: the readout and the face; the `*` follows either. */
    fk_font = ENV_FONT_SMALL; fk_view = 2;
    CHECK(prof_save(0, NULL) == PROF_OK && prof_slot(0, r) && r[PR_BVIEW] == (2 | 4) && prof_rec_valid(r));
    CHECK(prof_active_rec(r) == 0 && !prof_differs(r));
    fk_font = ENV_FONT_LARGE;
    CHECK(prof_differs(r));
    fk_font = ENV_FONT_SMALL; fk_view = 3;
    CHECK(prof_differs(r));
    /* A load and the keys' step: the readout and the face applied. */
    fk_rgb.h = 9; fk_view = 1; fk_font = ENV_FONT_REGULAR;
    CHECK(prof_save(1, NULL) == PROF_OK && prof_slot(1, q) && q[PR_BVIEW] == (1 | 8));
    fk_view = 3; fk_font = ENV_FONT_LARGE; fk_font_sets = 0;
    CHECK(prof_load(0) == PROF_OK && fk_view == 2 && fk_font == ENV_FONT_SMALL && fk_font_sets == 1);
    CHECK(prof_step(true, &s) == PROF_OK && s == 1 && fk_view == 1 && fk_font == ENV_FONT_REGULAR && fk_font_sets == 2);
    CHECK(prof_step(true, &s) == PROF_OK && s == 0 && fk_view == 2 && fk_font == ENV_FONT_SMALL && fk_font_sets == 3);
    /* A record saved before (the bits clear): Large. */
    uint8_t *e0 = &ee[PROF_BASE + PROF_REC_OFF(0)];
    e0[PR_BVIEW] = 2;
    recrc(e0);
    CHECK(prof_load(0) == PROF_OK && fk_view == 2 && fk_font == ENV_FONT_LARGE);
    /* Out of range: both face bits, a bit above them, a readout of 0. */
    static const uint8_t bad_bv[3] = {2 | 0x0C, 2 | 0x10, 4};
    for (int i = 0; i < 3; i++) {
        memcpy(q, r, PROF_REC);
        q[PR_BVIEW] = bad_bv[i];
        recrc(q);
        CHECK(!prof_rec_valid(q));
    }

    /* The Win/Mac switch: each side's face with its settings, the last record
     * carrying the side left (as left, unsaved changes too). */
    reset();
    prof_switch(false); ticks(1);
    fk_view = 2; fk_font = ENV_FONT_LARGE;
    CHECK(prof_save(0, NULL) == PROF_OK);   /* Windows' */
    prof_switch(true); ticks(3);             /* the Mac, none yet: Windows' kept */
    fk_view = 3; fk_font = ENV_FONT_REGULAR;
    CHECK(prof_save(1, NULL) == PROF_OK);   /* the Mac's */
    fk_font = ENV_FONT_SMALL;                /* changed, unsaved */
    prof_switch(false); ticks(3);
    CHECK(fk_switched == 1 && fk_view == 2 && fk_font == ENV_FONT_LARGE && last_state() == LAST_MAC &&
          B(PROF_REC_OFF(PROF_LAST) + PR_BVIEW) == (3 | 4));
    prof_switch(true); ticks(3);             /* the Mac's back from the last record, as left */
    CHECK(fk_switched == 2 && fk_view == 3 && fk_font == ENV_FONT_SMALL && last_state() == LAST_WIN &&
          B(PROF_REC_OFF(PROF_LAST) + PR_BVIEW) == 2);

    /* 4 and 5, flash.sh's live record: the face in it as in any record, the
     * crc over it; 5 applies it, and cancels the Font page's preview. */
    reset();
    fk_view = 2; fk_font = ENV_FONT_SMALL;
    CHECK(hid(4, 0, 0) && rpt[31] == PROF_OK && rpt[4 + PR_FIELDS] == PF_LIVE && rpt[4 + PR_BVIEW] == (2 | 4) &&
          rpt[4 + PR_CRC] == prof_crc8(&rpt[4 + PR_FIELDS], PR_CRC - PR_FIELDS) && prof_rec_valid(&rpt[4]));
    memcpy(small, &rpt[4], PROF_REC);
    fk_view = 3; fk_font = ENV_FONT_REGULAR;
    CHECK(hid(4, 0, 0) && rpt[4 + PR_BVIEW] == (3 | 8) && prof_rec_valid(&rpt[4]));
    memcpy(reg, &rpt[4], PROF_REC);
    fk_font = ENV_FONT_LARGE;
    CHECK(hid(4, 0, 0) && rpt[4 + PR_BVIEW] == 3 && prof_rec_valid(&rpt[4]));
    memcpy(large, &rpt[4], PROF_REC);
    fk_view = 1; fk_lcd = 0; fk_power = 3; calls[0] = '\0'; fk_font_sets = 0;
    int ext = fk_external[ME_DOM_FONT];
    CHECK(apply5(small) == PROF_OK && fk_view == 2 && fk_lcd == 52 && fk_power == 1 && fk_font == ENV_FONT_SMALL &&
          fk_font_sets == 1 && strcmp(calls, "eMHSELIICBFP") == 0 && fk_external[ME_DOM_FONT] == ext + 1);
    CHECK(hid(4, 0, 0) && memcmp(&rpt[4], small, PROF_REC) == 0);   /* flash.sh's round trip */
    CHECK(apply5(reg) == PROF_OK && fk_view == 3 && fk_font == ENV_FONT_REGULAR && fk_font_sets == 2);
    CHECK(apply5(large) == PROF_OK && fk_font == ENV_FONT_LARGE && fk_font_sets == 3);
    /* Refused with nothing applied: both bits; a crc that fails; an unknown
     * format; a recovery. */
    memcpy(q, small, PROF_REC);
    q[PR_BVIEW] |= 8;
    recrc(q);
    calls[0] = '\0';
    CHECK(apply5(q) == PROF_INVALID && calls[0] == '\0' && fk_font == ENV_FONT_LARGE && fk_font_sets == 3);
    memcpy(q, small, PROF_REC);
    q[PR_HUE] ^= 1;
    CHECK(apply5(q) == PROF_INVALID && calls[0] == '\0' && fk_font_sets == 3);
    memcpy(q, small, PROF_REC);
    q[PR_STATE] = 0x02;
    CHECK(apply5(q) == PROF_FORMAT && fk_font == ENV_FONT_LARGE && fk_font_sets == 3);
    fk_recovering = true;
    CHECK(apply5(small) == PROF_BUSY && calls[0] == '\0' && fk_font == ENV_FONT_LARGE && fk_font_sets == 3);
    fk_recovering = false;
    prof_test_reset();
}

int main(void) {
    test_codec();
    test_format_and_save();
    test_delete_and_load();
    test_hid_restore();
    test_hid_live();
    test_p5b();
    test_rename();
    test_switch();
    test_reset();
    test_switch_codex();
    test_font();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("profiles: all checks passed\n");
    return 0;
}
