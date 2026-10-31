/* A power cut at every durable write of a Win -> Mac flip, then the reboot
 * (plans/AUDIT-2026-10-31.md, F-012 and codex's review of its fix,
 * plans/review-codex-audit-batch3-2026-10-31.md, P1 and P2). The flip writes
 * the owner byte (PROF_OWNER_ADDR) first and last, and the boot finishes a
 * flip a cut stopped. Each case is cut before each of the flip's durable
 * steps in turn, the first a cut in the countdown with nothing written yet
 * (codex's P1: QMK's default layer was already the Mac's there), and the
 * board rebooted with the switch on the Mac, then on Windows (moved back
 * while off). What must hold: each side ends with its own settings or its
 * profile, never the other side's, and Windows never loses its own.
 * Then codex's P2: a backup taken on Windows, restored on the Mac, with and
 * without sub 8 (the live settings' side).
 *
 * Compiles the real menu/profiles.c (-DMENU_HOST_TEST). The fakes keep what
 * is DURABLE apart from RAM, as the audit's verify-036 did:
 *   - the profile block and the owner byte: ee[] is wear_leveling's RAM
 *     cache, d_ee[] the flash; each env_prof_write() is one durable step;
 *   - kb_eeconfig's block (lcd, indicators, clock, readout, font): RAM plus
 *     a dirty flag; env_settings_flush() writes it as one step, as
 *     kb_eeconfig_flush() does;
 *   - the RGB config: one step, as eeconfig_force_flush_rgb_matrix().
 * A cut at step N: steps before N durable, N and later not (a longjmp out of
 * the firmware). The reboot: RAM from the durable copies, prof_test_reset(),
 * the boot's switch reading (dip_switch_init()), then the 10 Hz ticks. */
#include <setjmp.h>
#include <stdio.h>
#include <string.h>

#include "menu_edit.h"
#include "menu_env.h"
#include "profiles.h"

void prof_test_reset(void);

typedef struct { uint8_t lcd, ind[2], clock, view, font; } kb_t;
static uint8_t   ee[1024], d_ee[1024];
static kb_t      kb, d_kb;
static env_rgb_t rgb, d_rgb;
static bool      kb_dirty, rgb_dirty;
static uint8_t   power = 1;

static int     step, cut_at = -1;
static jmp_buf cut_jmp;
static char    steplog[256][48];
static void durable(const char *what) {
    if (step == cut_at) longjmp(cut_jmp, 1);   /* not durable: the board browned out first */
    if (step < 256) snprintf(steplog[step], sizeof steplog[0], "%s", what);
    step++;
}

void env_prof_read(uint16_t addr, void *dst, uint8_t n) { memcpy(dst, &ee[addr], n); }
uint8_t env_prof_write(uint16_t addr, const void *src, uint8_t n) {
    char what[48];
    if (addr == PROF_OWNER_ADDR)
        snprintf(what, sizeof what, "owner byte 0x%02X", *(const uint8_t *)src);
    else
        snprintf(what, sizeof what, "block @%u n=%u first=0x%02X", (unsigned)(addr - PROF_BASE), n, *(const uint8_t *)src);
    memcpy(&ee[addr], src, n);   /* the cache first, as wear_leveling_write() */
    durable(what);
    memcpy(&d_ee[addr], src, n);
    return ENV_WR_OK;
}
bool env_recovering(void) { return false; }
static bool fk_pending;
void env_settings_flush(void) {
    if (kb_dirty) { durable("kb_eeconfig block (flush)"); d_kb = kb; kb_dirty = false; }
    durable("RGB config (forced flush)"); d_rgb = rgb; rgb_dirty = false;
    fk_pending = false;
}
void env_settings_touch(void) { fk_pending = true; kb_dirty = true; }
bool env_settings_pending(void) { return fk_pending; }

void env_rgb_get(env_rgb_t *c) { *c = rgb; }
void env_rgb_mode(uint8_t m, bool save) { if (rgb.enable) { rgb.mode = m < 1 ? 1 : m; rgb_dirty |= save; } }
void env_rgb_hsv(uint8_t h, uint8_t s, uint8_t v, bool save) {
    if (rgb.enable) { rgb.h = h; rgb.s = s; rgb.v = v; rgb_dirty |= save; }
}
void env_rgb_speed(uint8_t sp, bool save) { rgb.speed = sp; rgb_dirty |= save; }
void env_rgb_enable(bool on, bool save) { rgb.enable = on; rgb_dirty |= save; }
uint8_t env_lcd_level(void) { return kb.lcd; }
void    env_lcd_set(uint8_t l, bool save) { if (save && kb.lcd != l) kb_dirty = true; kb.lcd = l; }
uint8_t env_ind_level(uint8_t w) { return kb.ind[w]; }
void    env_ind_set(uint8_t w, uint8_t l, bool save) { if (save && kb.ind[w] != l) kb_dirty = true; kb.ind[w] = l; }
uint8_t env_clock_mode(void) { return kb.clock; }
void    env_clock_set(uint8_t m) { if (kb.clock != m) kb_dirty = true; kb.clock = m; }
uint8_t env_batt_view(void) { return kb.view; }
void    env_batt_view_set(uint8_t v) { if (kb.view != v) kb_dirty = true; kb.view = v; }
uint8_t env_power_mode(void) { return power; }
void    env_power_set(uint8_t m) { power = m; }
uint8_t env_font(void) { return kb.font; }
void    env_font_set(uint8_t f) { if (kb.font != f) kb_dirty = true; kb.font = f; }
void    menu_font_set(uint8_t f) { env_font_set(f); }
static const uint8_t fx_mode[3] = {1, 2, 3}, fx_id[3] = {1, 2, 4};
uint8_t env_effects(void) { return 3; }
uint8_t env_effect_mode(uint8_t i) { return i < 3 ? fx_mode[i] : 0; }
uint8_t env_effect_id(uint8_t i) { return i < 3 ? fx_id[i] : 0xFF; }
void    menu_edit_external(uint8_t d) { (void)d; }
void    env_prof_switched(uint8_t slot, uint8_t st) { (void)slot; (void)st; }
void    env_defaults(env_defaults_t *d) { *d = (env_defaults_t){{1, 36, 64, 191, 102, 1, 0xFF}, 80, 5, 5, 0, 1, 1}; }

static void ticks(int n) { for (int i = 0; i < n; i++) prof_tick(); }
/* kb_eeconfig's 5 s settle and rgb_matrix_task's deferred write, then the tick */
static void settle_all(void) {
    if (kb_dirty) { durable("kb settle"); d_kb = kb; kb_dirty = false; }
    if (rgb_dirty) { durable("rgb deferred"); d_rgb = rgb; rgb_dirty = false; }
    fk_pending = false;
    prof_tick();
}
/* The look: the screen level and the hue, both one value v. */
static void set_look(uint8_t v) { env_lcd_set(v, true); env_rgb_hsv(v, rgb.s, rgb.v, true); }
static int  look(void) { return kb.lcd == rgb.h ? kb.lcd : -1; }   /* -1: a mix of two sides' */
static uint8_t last_state(void) { return ee[PROF_BASE + PROF_REC_OFF(PROF_LAST) + PR_STATE]; }
static uint8_t last_lcd(void) { return ee[PROF_BASE + PROF_REC_OFF(PROF_LAST) + PR_LCD]; }
static void flip(bool mac) { prof_switch(mac); ticks(3); }
static void reboot(bool mac) {
    memcpy(ee, d_ee, sizeof ee);
    kb = d_kb; rgb = d_rgb; kb_dirty = rgb_dirty = fk_pending = false;
    prof_test_reset();
    prof_switch(mac);   /* dip_switch_init()'s reading */
    ticks(5);
}
static void fresh(void) {
    memset(ee, 0, sizeof ee); memset(d_ee, 0, sizeof d_ee);
    kb = (kb_t){52, {30, 60}, 4, 1, ENV_FONT_LARGE}; d_kb = kb;
    rgb = (env_rgb_t){2, 240, 215, 86, 127, 1, 0xFF}; d_rgb = rgb;
    kb_dirty = rgb_dirty = fk_pending = false;
    step = 0; cut_at = -1;
    prof_test_reset();
}

/* The states just before the flip under test, everything settled and durable:
 *   0 both: Windows' profile 20 (slot 0) at 25 (its `*`), the Mac's 90
 *     (slot 1) left at 95 (in the last record);
 *   1 Windows only: Windows' profile 20 at 25, the Mac none;
 *   2 the Mac only: the Mac's 90 left at 95 (in the last record), Windows
 *     none, at 25. */
static void setup(int k) {
    fresh();
    if (k == 2) {
        prof_switch(true); ticks(1);                  /* boot on the Mac */
        set_look(90); prof_save(1, NULL); settle_all();
        set_look(95); settle_all();
        flip(false); settle_all();                    /* Windows has none: the Mac's 95 kept, nothing loads */
        set_look(25); settle_all();
        return;
    }
    prof_switch(false); ticks(1);                     /* boot on Windows */
    set_look(20); prof_save(0, NULL); settle_all();
    if (k == 0) {
        flip(true); settle_all();                     /* to the Mac: Windows' kept */
        set_look(90); prof_save(1, NULL); settle_all();
        set_look(95); settle_all();
        flip(false); settle_all();                    /* to Windows: 20 back, the Mac's 95 kept */
    }
    set_look(25); settle_all();
}
static const char *const kname[3] = {"both profiled", "Windows only", "the Mac only"};
/* What each side may end with: its own settings, or (the documented loss, a
 * cut once the side left's record is in) the Mac's profile. Windows without
 * a profile keeps nothing of its own past a flip, so it shows the Mac's 95
 * once the flip happened, and its own 25 if the cut stopped it first. */
static bool mac_ok(int k, int v) { return k == 0 ? (v == 95 || v == 90) : k == 1 ? v == 25 : v == 95; }
static bool win_ok(int k, int v) { return k == 2 ? (v == 25 || v == 95) : v == 25; }

static int bad;

static void sweep(int k) {
    setup(k);
    int base = step;
    flip(true);
    int n = step - base, uncut = look();
    printf("\n%s: an uncut Win -> Mac flip, live %d, last record 0x%02X lcd %u; durable steps:\n", kname[k], uncut,
           last_state(), last_lcd());
    for (int i = 0; i < n; i++) printf("  step %d: %s\n", i, steplog[base + i]);
    printf("  cut before | owner, live at the cut | boot on the Mac: live, last  -> back on Windows | boot on Windows: live, then on the Mac\n");
    for (int c = 0; c <= n; c++) {
        int r[2][2];
        uint8_t o = 0, dl = 0;
        int     dlive = 0;
        for (int b = 0; b < 2; b++) {   /* b 0: the switch stays on the Mac; 1: moved back while off */
            setup(k);
            cut_at = step + c;
            if (setjmp(cut_jmp) == 0) flip(true);
            cut_at = -1;
            o = d_ee[PROF_OWNER_ADDR];
            dlive = d_kb.lcd == d_rgb.h ? d_kb.lcd : -1;
            reboot(b == 0);
            settle_all();
            r[b][0] = look();
            dl = last_state();
            flip(b != 0);   /* to the other side */
            settle_all();
            r[b][1] = look();
            if (b == 0) {
                bool ok = mac_ok(k, r[0][0]) && win_ok(k, r[0][1]);
                if (!ok) bad++;
                printf("  %2d%-9s | 0x%02X %4d          | %4d  0x%02X        -> %4d", c, c == n ? " (none)" : "", o, dlive,
                       r[0][0], dl, r[0][1]);
                (void)ok;
            } else {
                bool ok = win_ok(k, r[1][0]) && mac_ok(k, r[1][1]);
                if (!ok) bad++;
                bool ok0 = mac_ok(k, r[0][0]) && win_ok(k, r[0][1]);
                printf("            | %4d, %4d   %s\n", r[1][0], r[1][1], ok0 && ok ? "ok" : "BUG");
            }
        }
    }
}

/* Codex's P2: the backup taken on Windows (its live record Windows', its last
 * record the Mac's 95), restored while the switch is on the Mac, as the host
 * does (ak820profiles.py): begin, the pages, the commit, the live record, the
 * flush, then sub 8 with the backup's side, or not. */
static uint8_t rpt[32];
static bool    hid(uint8_t sub, uint8_t a4, uint8_t a5) {
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = sub; rpt[4] = a4; rpt[5] = a5;
    return prof_hid(rpt);
}
static void restore_cross(bool sub8) {
    uint8_t blk[PROF_PAGES * PROF_PAGE], live[PROF_REC];
    setup(0);
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        hid(0, p, 0);
        memcpy(&blk[p * PROF_PAGE], &rpt[6], PROF_PAGE);
    }
    hid(4, 0, 0);
    memcpy(live, &rpt[4], PROF_REC);
    flip(true); settle_all();          /* the Mac now: its 95 */
    set_look(60); settle_all();        /* and changed since: lost to the restore, as any restore's */
    hid(1, 0, 0x77);
    int okb = rpt[6] == PROF_OK;
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        hid(2, p, 0x77);
        memcpy(&rpt[6], &blk[p * PROF_PAGE], PROF_PAGE);
        rpt[3] = 2; rpt[4] = p; rpt[5] = 0x77;
        prof_hid(rpt);
        okb &= rpt[6] == PROF_OK;
    }
    hid(3, 0, 0x77);
    okb &= rpt[6] == PROF_OK;
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 5;
    memcpy(&rpt[4], live, PROF_REC);
    prof_hid(rpt);
    okb &= rpt[31] == PROF_OK;
    hid(6, 0, 0);
    okb &= rpt[4] == PROF_OK;
    if (sub8) {
        hid(8, PROF_SIDE_WIN, 0);
        okb &= rpt[5] == PROF_OK;
    }
    ticks(3); settle_all();
    int on_mac = look();
    uint8_t ls = last_state(), ll = last_lcd();
    reboot(true); settle_all();
    int reboot_mac = look();
    flip(false); settle_all();
    int on_win = look();
    flip(true); settle_all();
    int back_mac = look();
    bool ok = okb && on_mac == 95 && ls == (PS_LAST | PROF_SIDE_WIN) && ll == 25 && reboot_mac == 95 && on_win == 25 &&
              back_mac == 95;
    printf("restored on the Mac %s sub 8: live %d (95 the Mac's own), last 0x%02X lcd %u; rebooted %d; on Windows %d (25);"
           " on the Mac %d  %s\n",
           sub8 ? "with" : "without", on_mac, ls, ll, reboot_mac, on_win, back_mac,
           ok ? "ok" : sub8 ? "BUG" : "(the host's old restore: Windows' settings on the Mac, the Mac's lost)");
    if (sub8 && !ok) bad++;
}

int main(void) {
    for (int k = 0; k < 3; k++) sweep(k);
    printf("\n");
    restore_cross(false);
    restore_cross(true);
    printf("\n%d failure(s)\nRESULT: %s\n", bad, bad ? "FAIL" : "PASS");
    return bad ? 1 : 0;
}
