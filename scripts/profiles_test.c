/* Host test for keyboards/a_jazz/ak820pro/menu/profiles.c, the settings
 * profiles' store and HC_PROFILES (P5a, plans/SETTINGS-PROFILES-PLAN.md).
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
static int  fk_flushes;
void        env_settings_flush(void) { fk_flushes++; }

/* The live settings, and the setters' calls in order. */
static env_rgb_t fk_rgb = {2, 240, 215, 86, 127, 1, 0xFF};
static uint8_t   fk_lcd = 52, fk_ind[2] = {30, 60}, fk_clock = 4, fk_power = 1;
static bool      fk_hours;
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
bool    env_batt_hours(void) { return fk_hours; }
void    env_batt_hours_set(bool h) { fk_hours = h; call("B"); }
uint8_t env_power_mode(void) { return fk_power; }
void    env_power_set(uint8_t m) { fk_power = m; call("P"); }
/* The effects: modes 1, 2, 4 with stable ids 1, 2, 4 (a build with Breathing,
 * id 3, disabled). */
static const uint8_t fx_mode[3] = {1, 2, 3}, fx_id[3] = {1, 2, 4};
uint8_t env_effects(void) { return 3; }
uint8_t env_effect_mode(uint8_t i) { return i < 3 ? fx_mode[i] : 0; }
uint8_t env_effect_id(uint8_t i) { return i < 3 ? fx_id[i] : 0xFF; }
/* An open preview's rollback, by domain. */
static int fk_external[4];
void       menu_edit_external(uint8_t d) { if (d < 4) fk_external[d]++; }

/* --- Helpers -------------------------------------------------------------------- */

static void reset(void) {
    memset(ee, 0, sizeof ee);
    nlog = 0; fail_at = consolidate_at = -1;
    fk_recovering = false;
    fk_rgb = (env_rgb_t){2, 240, 215, 86, 127, 1, 0xFF};
    fk_lcd = 52; fk_ind[0] = 30; fk_ind[1] = 60; fk_clock = 4; fk_power = 1; fk_hours = false;
    calls[0] = '\0';
    memset(fk_external, 0, sizeof fk_external);
    prof_test_reset();
}
#define B(off) ee[PROF_BASE + (off)]
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
        {PR_RGB_ON, 2}, {PR_LCD, 101}, {PR_LOCKS, 101}, {PR_CHARGING, 101}, {PR_CLOCK, 6}, {PR_BVIEW, 0}, {PR_BVIEW, 3},
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
    /* The first save formats first: four states, the active byte, the magic last; then the save. */
    bool c = true;
    CHECK(prof_save(0, &c) == PROF_OK && !c);
    CHECK(nlog == 6 + 4);
    for (int s = 0; s < 4; s++) CHECK(wlog[s].addr == PROF_BASE + PROF_REC_OFF(s) && wlog[s].first == PS_EMPTY);
    CHECK(wlog[4].addr == PROF_BASE + PROF_OFF_ACTIVE && wlog[4].first == 0xFF);
    CHECK(wlog[5].addr == PROF_BASE + PROF_OFF_MAGIC && wlog[5].first == PROF_MAGIC_V1);
    /* The save: the state empty, the body (26 B), the state saved, the active byte. */
    CHECK(wlog[6].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[6].first == PS_EMPTY && wlog[6].n == 1);
    CHECK(wlog[7].addr == PROF_BASE + PROF_REC_OFF(0) + 1 && wlog[7].n == 26);
    CHECK(wlog[8].addr == PROF_BASE + PROF_REC_OFF(0) && wlog[8].first == PS_SAVED_V1 && wlog[8].n == 1);
    CHECK(wlog[9].addr == PROF_BASE + PROF_OFF_ACTIVE && wlog[9].first == 0);
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
    nlog = 0; fail_at = 5;
    CHECK(prof_save(0, NULL) == PROF_WRITE_FAILED && prof_write_failed());
    fail_at = -1;
    CHECK(prof_save(0, NULL) == PROF_WRITE_FAILED && nlog == 6);
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
    CHECK(prof_save(9, NULL) == PROF_BAD);
}

static void test_delete_and_load(void) {
    reset();
    uint8_t r[PROF_REC];
    fk_rgb.h = 100;
    CHECK(prof_save(0, NULL) == PROF_OK);
    fk_rgb.h = 200; fk_lcd = 10; fk_clock = 1; fk_hours = true;
    CHECK(prof_save(1, NULL) == PROF_OK && prof_active() == 1);
    /* Delete: the state alone (its crc still good), and the active byte to none if it was active. */
    nlog = 0;
    CHECK(prof_delete(1) == PROF_OK && nlog == 2 && !prof_slot(1, r) && prof_active() == 0xFF);
    CHECK(prof_delete(0) == PROF_OK && nlog == 3 && prof_active() == 0xFF);
    /* The active byte pointing at an empty slot reads as none. */
    CHECK(prof_save(0, NULL) == PROF_OK && prof_active() == 0);
    B(PROF_REC_OFF(0)) = 0x07;
    CHECK(prof_active() == 0xFF);
    B(PROF_REC_OFF(0)) = PS_SAVED_V1;
    /* Load, with the lights off: on unsaved first, then the mode, HSV, speed, the enable last at the record's value. */
    CHECK(prof_save(2, NULL) == PROF_OK);   /* h 200, lcd 10, clock 1, hours */
    fk_rgb.enable = 0; fk_rgb.h = 5; fk_lcd = 90; fk_clock = 0; fk_hours = false; fk_power = 3;
    calls[0] = '\0';
    CHECK(prof_load(2) == PROF_OK);
    CHECK(strcmp(calls, "eMHSELIICB") == 0 && fk_rgb.enable == 1 && fk_rgb.h == 200 && fk_lcd == 10 && fk_clock == 1 &&
          fk_hours && fk_power == 3 && prof_active() == 2);
    /* A record saved off stays off: the enable last, saved, at its value. */
    fk_rgb.enable = 0;
    CHECK(prof_save(3, NULL) == PROF_OK);
    fk_rgb.enable = 1;
    calls[0] = '\0';
    CHECK(prof_load(3) == PROF_OK && fk_rgb.enable == 0 && strcmp(calls, "eMHSDLIICB") == 0);
    /* An effect id this build lacks (Breathing, 3): skipped, the rest loads. */
    uint8_t *rec = &ee[PROF_BASE + PROF_REC_OFF(2)];
    rec[PR_EFFECT] = 3;
    rec[PR_CRC]    = prof_crc8(&rec[PR_FIELDS], PR_CRC - PR_FIELDS);
    fk_rgb.mode = 1; fk_rgb.h = 0;
    calls[0] = '\0';
    CHECK(prof_load(2) == PROF_OK_EFFECT_SKIPPED && fk_rgb.mode == 1 && fk_rgb.h == 200 && strcmp(calls, "eHSELIICB") == 0);
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
static void make_image(uint8_t *img) {
    reset();
    fk_rgb.h = 11;
    prof_save(0, NULL);
    fk_rgb.h = 22;
    prof_save(3, NULL);
    memcpy(img, &ee[PROF_BASE], PROF_BLOCK_SIZE);
}
static void send_pages(const uint8_t *img, uint8_t token, uint8_t skip_page) {
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        if (p == skip_page) continue;
        hid(2, p, token);
        uint8_t n = (uint8_t)(PROF_BLOCK_SIZE - p * PROF_PAGE < PROF_PAGE ? PROF_BLOCK_SIZE - p * PROF_PAGE : PROF_PAGE);
        memcpy(&rpt[6], &img[p * PROF_PAGE], n);
        if (p == 0) rpt[6] = 0x55;   /* the host's magic: ignored */
        CHECK(prof_hid(rpt) && rpt[6] == PROF_OK);
    }
}

static void test_hid_restore(void) {
    uint8_t img[PROF_BLOCK_SIZE], r[PROF_REC];
    make_image(img);
    /* Read: five pages of 26 B, zero past the end. */
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        CHECK(hid(0, p, 0) && rpt[5] == PROF_OK);
        uint8_t n = (uint8_t)(p < 4 ? 26 : 6);
        CHECK(memcmp(&rpt[6], &img[p * 26], n) == 0);
        if (p == 4) for (int i = 6 + 6; i < 32; i++) CHECK(rpt[i] == 0);
    }
    CHECK(hid(0, 5, 0) && rpt[5] == PROF_BAD);
    /* A good restore onto a wiped block. */
    memset(&ee[PROF_BASE], 0, PROF_BLOCK_SIZE);
    CHECK(hid(1, 0, 0x5A) && rpt[6] == PROF_OK && B(PROF_OFF_MAGIC) == 0);
    send_pages(img, 0x5A, 0xFF);
    CHECK(B(PROF_OFF_MAGIC) == 0);   /* the magic masked until the commit */
    nlog = 0;
    CHECK(hid(3, 0, 0x5A) && rpt[6] == PROF_OK && !prof_restore_open());
    CHECK(wlog[nlog - 1].addr == PROF_BASE + PROF_OFF_MAGIC && wlog[nlog - 1].first == PROF_MAGIC_V1);   /* the magic last */
    CHECK(memcmp(&ee[PROF_BASE], img, PROF_BLOCK_SIZE) == 0 && prof_active() == 3 && prof_slot(0, r) && r[PR_HUE] == 11);
    /* A missing page: refused, the block unformatted. */
    CHECK(hid(1, 0, 0x5B) && rpt[6] == PROF_OK);
    send_pages(img, 0x5B, 2);
    CHECK(hid(3, 0, 0x5B) && rpt[6] == PROF_INCOMPLETE && !prof_formatted() && !prof_restore_open());
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
    /* An active byte pointing at an empty slot: normalized to none at the commit. */
    uint8_t norm[PROF_BLOCK_SIZE];
    memcpy(norm, img, sizeof norm);
    norm[PROF_OFF_ACTIVE] = 1;
    CHECK(hid(1, 0, 0x06) && rpt[6] == PROF_OK);
    send_pages(norm, 0x06, 0xFF);
    CHECK(hid(3, 0, 0x06) && rpt[6] == PROF_OK && B(PROF_OFF_ACTIVE) == 0xFF && prof_formatted());
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
    CHECK(hid(2, 1, 0x08) && rpt[6] == PROF_WRITE_FAILED && !prof_restore_open());
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
    CHECK(!hid(7, 0, 0) && !hid(0x42, 0, 0));
    CHECK(hid(0x40, 1, 0) && rpt[5] == PROF_OK && prof_active() == 1);
    CHECK(hid(0x41, 1, 0) && rpt[5] == PROF_OK && prof_active() == 0xFF);
}

int main(void) {
    test_codec();
    test_format_and_save();
    test_delete_and_load();
    test_hid_restore();
    test_hid_live();
    if (fails) {
        printf("%d check(s) failed\n", fails);
        return 1;
    }
    printf("profiles: all checks passed\n");
    return 0;
}
