/* A power cut at every durable write of a Win -> Mac flip, then the reboot
 * (plans/AUDIT-2026-10-31.md, F-012 and codex's review of its fix,
 * plans/review-codex-audit-batch3-2026-10-31.md, P1 and P2, and its verify).
 * The flip writes the owner byte (PROF_OWNER_ADDR) first and last, and the
 * boot finishes a flip a cut stopped. Each case is cut before each of the
 * flip's durable steps in turn, the first a cut in the countdown with nothing
 * written yet (codex's P1: QMK's default layer was already the Mac's there),
 * and the board rebooted with the switch on the Mac, then on Windows (moved
 * back while off). What must hold: each side ends with its own settings or
 * its profile, never the other side's, and Windows never loses its own.
 * Codex's verify added:
 *   - a second cut inside the boot's recovery of each first cut;
 *   - a backup taken on Windows restored on the Mac in the host's order (the
 *     pages, the live record applied and flushed, the commit naming its side,
 *     the flip it arms), cut at every step;
 *   - failures injected in place of cuts: a profile write or a settings
 *     line that doesn't land (its cache updated, its flash not), the run going
 *     on; and a control that drops the flush's status as QMK's EEPROM driver
 *     did, which must publish a settled owner over a mix;
 *   - a pending menu choice (a Load not yet settled) at the flip;
 *   - Load, Save and an apply refused until the boot's check has run.
 *
 * Compiles the real menu/profiles.c (-DMENU_HOST_TEST). The fakes keep what
 * is DURABLE apart from RAM, as the audit's verify-036 did, in wear
 * leveling's lines of 4 value bytes:
 *   - the profile block and the owner byte: ee[] is wear_leveling's RAM
 *     cache, d_ee[] the flash; a write of n bytes is ceil(n / 4) durable
 *     lines;
 *   - kb_eeconfig's block (lcd, indicators, clock, readout, font): RAM plus
 *     a dirty flag; a flush writes it as two lines, as kb_eeconfig_flush()'s
 *     one block write is (the screen level in the first);
 *   - the RGB config: two lines (the hue in the first), as
 *     eeconfig_force_flush_rgb_matrix().
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
static kb_t      kb, d_kb, c_kb;      /* RAM, the flash, wear leveling's cache of them */
static env_rgb_t rgb, d_rgb, c_rgb;
static bool      wl_failed_ever;       /* a line failed since the boot: wear_leveling_failures() nonzero */
static bool      kb_dirty, rgb_dirty;
static uint8_t   power = 1;

static int     step, cut_at = -1, fail_at = -1;
static bool    flush_reports = true;   /* false: the status dropped, as QMK's EEPROM driver does */
static jmp_buf cut_jmp;
static char    steplog[256][48];
static void durable(const char *what) {
    if (step == cut_at) longjmp(cut_jmp, 1);   /* not durable: the board browned out first */
    if (step < 256) snprintf(steplog[step], sizeof steplog[0], "%s", what);
    step++;
}
/* One line: false when it is the injected failure (consumes its step, lands nothing). */
static bool line(const char *what) {
    if (step == fail_at) {
        if (step < 256) snprintf(steplog[step], sizeof steplog[0], "FAILED %s", what);
        step++;
        wl_failed_ever = true;
        return false;
    }
    durable(what);
    return true;
}

void env_prof_read(uint16_t addr, void *dst, uint8_t n) { memcpy(dst, &ee[addr], n); }
uint8_t env_prof_write(uint16_t addr, const void *src, uint8_t n) {
    memcpy(&ee[addr], src, n);   /* the cache first, as wear_leveling_write() */
    for (uint8_t o = 0; o < n; o += 4) {
        uint8_t k = (uint8_t)(n - o < 4 ? n - o : 4);
        char    what[48];
        if (addr == PROF_OWNER_ADDR)
            snprintf(what, sizeof what, "owner byte 0x%02X", *(const uint8_t *)src);
        else
            snprintf(what, sizeof what, "block @%u n=%u line %u first=0x%02X", (unsigned)(addr - PROF_BASE), n, o / 4u,
                     ((const uint8_t *)src)[o]);
        if (!line(what)) return ENV_WR_FAILED;   /* wear_leveling_write() stops at the line that failed */
        memcpy(&d_ee[addr + o], (const uint8_t *)src + o, k);
    }
    return ENV_WR_OK;
}
bool env_recovering(void) { return false; }
static bool fk_pending;
/* kb_eeconfig's block, then the RGB config's, each in its lines; the cache
 * first, so a failed line leaves its bytes there, and a write of bytes the
 * cache already holds is skipped, as wear_leveling_write()'s. */
static bool kb_write(const char *why) {
    char w[48];
    if (!memcmp(&c_kb, &kb, sizeof kb)) return true;
    c_kb = kb;
    snprintf(w, sizeof w, "kb_eeconfig line 0 (%s)", why);
    if (!line(w)) return false;
    d_kb.lcd = kb.lcd; d_kb.ind[0] = kb.ind[0]; d_kb.ind[1] = kb.ind[1]; d_kb.clock = kb.clock;
    snprintf(w, sizeof w, "kb_eeconfig line 1 (%s)", why);
    if (!line(w)) return false;
    d_kb.view = kb.view; d_kb.font = kb.font;
    return true;
}
static bool rgb_write(const char *why) {
    char w[48];
    if (!memcmp(&c_rgb, &rgb, sizeof rgb)) return true;
    c_rgb = rgb;
    snprintf(w, sizeof w, "RGB line 0 (%s)", why);
    if (!line(w)) return false;
    d_rgb.enable = rgb.enable; d_rgb.mode = rgb.mode; d_rgb.h = rgb.h; d_rgb.s = rgb.s;
    snprintf(w, sizeof w, "RGB line 1 (%s)", why);
    if (!line(w)) return false;
    d_rgb.v = rgb.v; d_rgb.speed = rgb.speed;
    return true;
}
bool env_settings_flush(void) {
    bool ok = true;
    if (kb_dirty) { ok = kb_write("flush"); kb_dirty = false; }
    ok = rgb_write("forced flush") && ok; rgb_dirty = false;
    fk_pending = false;
    /* reported: any failure since the boot (the firmware's sticky count); the
     * control, as QMK's driver: nothing. */
    (void)ok;
    return !wl_failed_ever || !flush_reports;
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
    if (kb_dirty) { (void)kb_write("settle"); kb_dirty = false; }
    if (rgb_dirty) { (void)rgb_write("deferred"); rgb_dirty = false; }
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
    kb = c_kb = d_kb; rgb = c_rgb = d_rgb; kb_dirty = rgb_dirty = fk_pending = false;
    wl_failed_ever = false;
    prof_test_reset();
    prof_switch(mac);   /* dip_switch_init()'s reading */
    ticks(5);
}
static void fresh(void) {
    memset(ee, 0, sizeof ee); memset(d_ee, 0, sizeof d_ee);
    kb = (kb_t){52, {30, 60}, 4, 1, ENV_FONT_LARGE}; d_kb = c_kb = kb;
    rgb = (env_rgb_t){2, 240, 215, 86, 127, 1, 0xFF}; d_rgb = c_rgb = rgb;
    kb_dirty = rgb_dirty = fk_pending = false;
    wl_failed_ever = false;
    step = 0; cut_at = fail_at = -1;
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
    if (k == 3) {   /* both profiled, then Windows' profile loaded (20) and its choice still pending at the flip */
        setup(0);
        prof_load(0);
        return;
    }
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
static const char *const kname[4] = {"both profiled", "Windows only", "the Mac only", "both, a Load pending"};
/* What each side may end with: its own settings, or (the documented loss, a
 * cut once the side left's record is in) the Mac's profile. Windows without
 * a profile keeps nothing of its own past a flip, so it shows the Mac's 95
 * once the flip happened, and its own 25 if the cut stopped it first. */
static bool mac_ok(int k, int v) { return k == 0 || k == 3 ? (v == 95 || v == 90) : k == 1 ? v == 25 : v == 95; }
static bool win_ok(int k, int v) {
    return k == 2 ? (v == 25 || v == 95) : k == 3 ? (v == 20 || v == 25) : v == 25;   /* 3: the Load's 20, or 25 unflushed */
}

static int bad, runs;

/* The flip under test, cut at its step c, then a second cut at step c2 of the
 * boot that recovers it (c2 < 0: none), then a clean boot with the switch on
 * the Mac (mac) or moved back to Windows, and the flip to the other side.
 * Returns ok; r[] the looks on the two sides, o the owner left by the cut. */
static bool cut_run(int k, int c, int c2, int w2_from, bool mac, int r[2], uint8_t *o) {
    setup(k);
    cut_at = step + c;
    if (setjmp(cut_jmp) == 0) flip(true);
    cut_at = -1;
    *o = d_ee[PROF_OWNER_ADDR];
    if (c2 >= 0) {
        memcpy(ee, d_ee, sizeof ee);
        kb = c_kb = d_kb; rgb = c_rgb = d_rgb; kb_dirty = rgb_dirty = fk_pending = false;
        wl_failed_ever = false;
        prof_test_reset();
        cut_at = step + c2;
        if (setjmp(cut_jmp) == 0) { prof_switch(mac); ticks(5); settle_all(); }
        cut_at = -1;
    }
    reboot(mac);
    settle_all();
    r[0] = look();
    flip(!mac);
    settle_all();
    r[1] = look();
    runs++;
    /* A second cut in the recovering boot's flip TO Windows (the switch moved
     * back; w2_from its first step, the owner byte OW_MOVING | Windows): then
     * Windows is the side arrived at, and the documented loss is its own, its
     * changes since its profile (20). Nowhere else (codex's verify). */
    bool w2 = !mac && k != 2 && w2_from >= 0 && c2 >= w2_from;
    return mac ? mac_ok(k, r[0]) && (win_ok(k, r[1]) || (w2 && r[1] == 20))
               : (win_ok(k, r[0]) || (w2 && r[0] == 20)) && mac_ok(k, r[1]);
}

/* The steps a clean boot takes after the flip cut at c (the recovery's), and
 * in *w2_from the first of its flip toward Windows (-1: none). */
static int boot_steps(int k, int c, bool mac, int *w2_from) {
    setup(k);
    cut_at = step + c;
    if (setjmp(cut_jmp) == 0) flip(true);
    cut_at = -1;
    int base = step;
    reboot(mac);
    settle_all();
    *w2_from = -1;
    for (int i = base; i < step && i < 256; i++) {
        char want[48];
        snprintf(want, sizeof want, "owner byte 0x%02X", 0x60 | PROF_SIDE_WIN);
        if (!strcmp(steplog[i], want)) { *w2_from = i - base; break; }
    }
    return step - base;
}

static void sweep(int k) {
    setup(k);
    int base = step;
    flip(true);
    int n = step - base, uncut = look();
    printf("\n%s: an uncut Win -> Mac flip, live %d, last record 0x%02X lcd %u; durable steps:\n", kname[k], uncut,
           last_state(), last_lcd());
    for (int i = 0; i < n; i++) printf("  step %d: %s\n", i, steplog[base + i]);
    printf("  cut before | owner | boot on the Mac: live -> on Windows | boot on Windows: live -> on the Mac | recovery cut\n");
    for (int c = 0; c <= n; c++) {
        int     rm[2], rw[2], nested = 0, nested_bad = 0;
        uint8_t o;
        bool    okm = cut_run(k, c, -1, -1, true, rm, &o);
        bool    okw = cut_run(k, c, -1, -1, false, rw, &o);
        if (!okm) bad++;
        if (!okw) bad++;
        /* A second cut at each step of the recovering boot, either way. */
        for (int b = 0; b < 2; b++) {
            int w2_from, n2 = boot_steps(k, c, b == 0, &w2_from);
            for (int c2 = 0; c2 < n2; c2++) {
                int     r2[2];
                uint8_t o2;
                nested++;
                if (!cut_run(k, c, c2, w2_from, b == 0, r2, &o2)) {
                    nested_bad++;
                    if (nested_bad <= 3)
                        printf("    BUG: cut %d, then the %s boot's step %d: %d -> %d\n", c, b ? "Windows" : "Mac", c2,
                               r2[0], r2[1]);
                }
            }
        }
        bad += nested_bad;
        printf("  %2d%-9s | 0x%02X  | %4d -> %4d               | %4d -> %4d                | %d of %d ok   %s\n", c,
               c == n ? " (none)" : "", o, rm[0], rm[1], rw[0], rw[1], nested - nested_bad, nested,
               okm && okw && !nested_bad ? "ok" : "BUG");
    }
}

/* The host's restore (ak820profiles.py): a backup taken on Windows (its live
 * record Windows' 25, its last record the Mac's 95) restored while the switch
 * is on the Mac, whose live settings changed since (60). The pages; the live
 * record applied and flushed with the block unpublished; the commit naming
 * the live settings' side ([7], Windows); the flip it arms. */
static uint8_t rpt[32];
static bool    hid(uint8_t sub, uint8_t a4, uint8_t a5) {
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = sub; rpt[4] = a4; rpt[5] = a5;
    return prof_hid(rpt);
}
static uint8_t r_blk[PROF_PAGES * PROF_PAGE], r_live[PROF_REC];
static void restore_setup(void) {
    setup(0);
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        hid(0, p, 0);
        memcpy(&r_blk[p * PROF_PAGE], &rpt[6], PROF_PAGE);
    }
    hid(4, 0, 0);
    memcpy(r_live, &rpt[4], PROF_REC);
    flip(true); settle_all();          /* the Mac now: its 95 */
    set_look(60); settle_all();        /* and changed since: lost to the restore, as any restore's */
}
/* Returns the statuses all OK. */
static bool restore_run(uint8_t side_byte) {
    bool ok = true;
    hid(1, 0, 0x77);
    ok &= rpt[6] == PROF_OK;
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        memset(rpt, 0, sizeof rpt);
        rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 2; rpt[4] = p; rpt[5] = 0x77;
        memcpy(&rpt[6], &r_blk[p * PROF_PAGE], PROF_PAGE);
        prof_hid(rpt);
        ok &= rpt[6] == PROF_OK;
    }
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 5;
    memcpy(&rpt[4], r_live, PROF_REC);
    prof_hid(rpt);
    ok &= rpt[31] == PROF_OK;
    hid(6, 0, 0);
    ok &= rpt[4] == PROF_OK;
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 3; rpt[5] = 0x77; rpt[7] = side_byte;
    prof_hid(rpt);
    ok &= rpt[6] == PROF_OK;
    ticks(3);   /* the flip it armed */
    settle_all();
    return ok;
}

static char r_log[160][48];
static void restore_sweep(void) {
    restore_setup();
    int base = step;
    bool okst = restore_run(1u + PROF_SIDE_WIN);
    int  n = step - base, live = look();
    for (int i = 0; i < n && i < 160; i++) memcpy(r_log[i], steplog[base + i], sizeof r_log[0]);
    uint8_t ls = last_state(), ll = last_lcd();
    hid(7, 0, 0);
    bool confirmed = rpt[9] == 1u + PROF_SIDE_MAC && rpt[10] == 0x84u;   /* settled on the Mac, the switch there */
    reboot(true); settle_all();
    int rb = look();
    flip(false); settle_all();
    int w = look();
    flip(true); settle_all();
    int m = look();
    bool ok = okst && confirmed && live == 95 && ls == (PS_LAST | PROF_SIDE_WIN) && ll == 25 && rb == 95 && w == 25 && m == 95;
    printf("\nthe restore on the Mac, uncut: live %d (95 the Mac's own), last 0x%02X lcd %u, sub 7 [9] %u [10] 0x%02X;"
           " rebooted %d; on Windows %d (25); on the Mac %d  %s\n", live, ls, ll, rpt[9], rpt[10], rb, w, m, ok ? "ok" : "BUG");
    if (!ok) bad++;
    int cuts_bad = 0, unpub = 0;
    for (int c = 0; c <= n; c++) {
        restore_setup();
        cut_at = step + c;
        if (setjmp(cut_jmp) == 0) restore_run(1u + PROF_SIDE_WIN);
        cut_at = -1;
        reboot(true); settle_all();
        bool f = prof_formatted();
        int  m0 = look();
        flip(false); settle_all();
        int w0 = look();
        flip(true); settle_all();
        int m1 = look();
        runs++;
        /* Nothing durable: as before the restore (the Mac's own 60). Before the commit's magic: no profiles,
         * nothing a side's (the host failed, its backup kept). After it: each side its own. */
        bool okc = c == 0 ? f && m0 == 60 && w0 == 25 && m1 == 60
                 : !f     ? true
                          : (m0 == 95 || m0 == 90) && w0 == 25 && (m1 == 95 || m1 == 90);
        if (!f) unpub++;
        if (!okc) {
            cuts_bad++;
            if (cuts_bad <= 5) printf("  BUG: the restore cut before step %d (%s): Mac %d, Windows %d, Mac %d\n", c,
                                      c < n && c < 160 ? r_log[c] : "none", m0, w0, m1);
        }
    }
    printf("the restore cut at each of its %d steps: %d with the block unpublished (no profiles), %d of the rest ok\n",
           n + 1, unpub, n + 1 - unpub - cuts_bad);
    bad += cuts_bad;
}

/* Codex's verify, finding 1: the live record applied, then its deferred write
 * (kb_eeconfig's settle, RGB's) fails before the host's flush: the bytes are
 * in the cache, so the flush skips them as unchanged. The flush must report
 * the failure and the commit must not publish; the control (the status
 * dropped) publishes the owner over settings that never landed. */
static bool restore_deferred_fail(bool reports) {
    flush_reports = reports;
    restore_setup();
    bool ok = true;
    hid(1, 0, 0x77);
    for (uint8_t p = 0; p < PROF_PAGES; p++) {
        memset(rpt, 0, sizeof rpt);
        rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 2; rpt[4] = p; rpt[5] = 0x77;
        memcpy(&rpt[6], &r_blk[p * PROF_PAGE], PROF_PAGE);
        prof_hid(rpt);
    }
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 5;
    memcpy(&rpt[4], r_live, PROF_REC);
    prof_hid(rpt);
    fail_at = step;   /* the first deferred line */
    if (kb_dirty) { (void)kb_write("settle"); kb_dirty = false; }
    if (rgb_dirty) { (void)rgb_write("deferred"); rgb_dirty = false; }
    fail_at = -1;
    hid(6, 0, 0);
    uint8_t fl = rpt[4];
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 3; rpt[5] = 0x77; rpt[7] = 1u + PROF_SIDE_WIN;
    prof_hid(rpt);
    uint8_t cm = rpt[6];
    bool published = d_ee[PROF_BASE + PROF_OFF_MAGIC] == PROF_MAGIC_V4;
    ok = fl == PROF_WRITE_FAILED && cm != PROF_OK && !published;
    printf("  %s: the flush %u, the commit %u, the block %s  %s\n", reports ? "reported" : "the control (dropped)", fl, cm,
           published ? "published" : "unpublished", reports ? (ok ? "ok" : "BUG") : (published ? "(as it must)" : "BUG"));
    flush_reports = true;
    return reports ? ok : published;
}

/* A write that fails in place of each step of the flip, the run going on, then
 * the reboot. flush_reports false: the control, the flush's status dropped. */
static int fail_sweep(int k, bool reports) {
    flush_reports = reports;
    setup(k);
    int base = step;
    flip(true);
    int n = step - base, nbad = 0;
    for (int f = 0; f < n; f++) {
        for (int b = 0; b < 2; b++) {
            setup(k);
            fail_at = step + f;
            flip(true);
            settle_all();
            fail_at = -1;
            reboot(b == 0);
            settle_all();
            int r0 = look();
            flip(b != 0);
            settle_all();
            int r1 = look();
            runs++;
            bool ok = b == 0 ? mac_ok(k, r0) && win_ok(k, r1) : win_ok(k, r0) && mac_ok(k, r1);
            if (!ok) {
                nbad++;
                if (reports && nbad <= 3)
                    printf("  BUG: %s, step %d (%s) failed: boot on %s %d -> %d\n", kname[k], f, steplog[base + f],
                           b ? "Windows" : "the Mac", r0, r1);
            }
        }
    }
    flush_reports = true;
    return nbad;
}

/* Until the boot's check has read the owner byte, SD_SETTLED is the switch's
 * reading: Load, Save, Reset, a restore's begin and an apply are refused. */
static void preboot(void) {
    setup(0);
    flip(true); settle_all();
    memcpy(ee, d_ee, sizeof ee);
    kb = c_kb = d_kb; rgb = c_rgb = d_rgb;
    wl_failed_ever = false;
    prof_test_reset();
    prof_switch(false);   /* the boot's reading, no tick yet */
    uint8_t ld = prof_load(0), sv = prof_save(2, NULL), rs = prof_reset();
    hid(1, 0, 0x55);
    uint8_t bg = rpt[6];
    memset(rpt, 0, sizeof rpt);
    rpt[0] = 0x07; rpt[1] = 0x13; rpt[2] = 0x10; rpt[3] = 5;
    memcpy(&rpt[4], r_live, PROF_REC);
    prof_hid(rpt);
    uint8_t ap = rpt[31];
    hid(7, 0, 0);
    uint8_t pend = rpt[10];
    ticks(1);
    uint8_t ld2 = prof_load(0);
    bool ok = ld == PROF_BUSY && sv == PROF_BUSY && rs == PROF_BUSY && bg == PROF_BUSY && ap == PROF_BUSY &&
              (pend & 1u) && ld2 == PROF_OK;
    printf("\nbefore the boot's check: Load %u, Save %u, Reset %u, begin %u, apply %u (3 busy), sub 7 [10] 0x%02X;"
           " after a tick, Load %u  %s\n", ld, sv, rs, bg, ap, pend, ld2, ok ? "ok" : "BUG");
    if (!ok) bad++;
}

int main(void) {
    for (int k = 0; k < 4; k++) sweep(k);
    restore_setup();   /* r_live for preboot() */
    restore_sweep();
    printf("\nfailures in place of each step of the flip, the run going on, then the reboot:\n");
    int fb = 0, ctl = 0;
    for (int k = 0; k < 4; k++) fb += fail_sweep(k, true);
    for (int k = 0; k < 4; k++) ctl += fail_sweep(k, false);
    printf("  %d bad with the flush's status reported; the control (the status dropped, as before): %d bad%s\n", fb, ctl,
           ctl ? " (as it must: a settled owner over a mix)" : "  BUG: the control should fail");
    bad += fb + (ctl ? 0 : 1);
    printf("\na deferred write of the restore's live record fails before the host's flush:\n");
    if (!restore_deferred_fail(true)) bad++;
    if (!restore_deferred_fail(false)) bad++;
    preboot();
    printf("\n%d run(s), %d failure(s)\nRESULT: %s\n", runs, bad, bad ? "FAIL" : "PASS");
    return bad ? 1 : 0;
}
