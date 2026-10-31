/* A torn wear-leveling log line is refused, not replayed
 * (plans/AUDIT-2026-10-31.md, F-010; first written as the audit's verify-037).
 * On the SN32's 8-byte lines an interrupted program can only drop logical
 * 1-bits, so before the fix a torn multi-byte line kept its type, shrank its
 * address and length, and was replayed as a valid write to a lower address:
 * the store wiped (the magic broken) or another setting silently changed.
 * Now each such line carries a CRC-8 in byte 7, and one that fails ends the
 * playback, keeping what came before.
 *
 * The original description follows. */
/* verify-037: does the emulated EEPROM replay a half-programmed write-log line
 * as a valid write?
 *
 * Everything between the board's setters and the flash is QMK's real code,
 * compiled by path from the working tree (build.sh here):
 *   keyboards/a_jazz/ak820pro/kb_eeconfig.c          the kb datablock's owner
 *   quantum/nvm/eeprom/nvm_eeconfig.c                 eeconfig's EEPROM layout
 *   drivers/eeprom/eeprom_driver.c, eeprom_wear_leveling.c
 *   quantum/wear_leveling/wear_leveling.c             the log and its playback
 *   platforms/chibios/drivers/wear_leveling/wear_leveling_efl.c   the backing store
 *   lib/fnv/hash_64a.c                                the consolidated copy's hash
 * Only the flash itself is faked (fake HAL below), as hal_efl_lld.c drives the
 * SN32F290: 8-byte lines, 1 KB sectors, erased = 0xFF, a line that is not
 * erased refused.
 *
 * A power cut is a fork()ed "session" that _exit()s inside the chosen line
 * program: RAM dies with the child, the flash (MAP_SHARED) survives, and the
 * next session boots from it with fresh statics, as a reset does. A cut inside
 * a program leaves a subset of the cells that were meant to go 1 -> 0: a cell
 * meant to stay erased cannot be programmed by a cut. The SHAPE of the subset
 * on this chip is not known (needs the bench); each scenario names its shape.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include "hal.h"
#include "wear_leveling.h"
#include "wear_leveling_drivers.h"
#include "wear_leveling_internal.h"   /* write_log_entry_t and the entry macros */
#include "eeprom.h"
#include "eeprom_driver.h"
#include "nvm_eeconfig.h"
#include "nvm_eeprom_eeconfig_internal.h"
#include "keycode_config.h"
#include "rgb_matrix_types.h"
#include "kb_eeconfig.h"
#include "indicators.h"
#include "bluetooth/ch582f_ajazz.h"

#define CUT_EXIT 42
#define LOGSTART ((WEAR_LEVELING_LOGICAL_SIZE) + 8u)

/* ---------------- shared state: the flash and the cut ---------------- */
struct ctl {
    int      cut_at;      /* the line program (1-based, this session) the cut lands in; 0 none */
    uint64_t survive;     /* logical bits of that line that got programmed before the cut */
    int      programs;
    int      cut_fired;
};
struct result {
    int      enabled;     /* nvm_eeconfig_is_enabled(): quantum_init() runs eeconfig_init() when 0 */
    uint8_t  img[WEAR_LEVELING_LOGICAL_SIZE];
    uint8_t  line[8];     /* the first log line as the store reads it (logical) */
};
static uint8_t       *flash;   /* FLASH_SIZE bytes, MAP_SHARED */
static struct ctl    *ctl;
static struct result *res;
static uint32_t       now_ms = 1000;

/* ---------------- fake HAL (the flash), as hal_efl_lld.c ---------------- */
EFlashDriver EFLD1;
static flash_descriptor_t desc = {
    .attributes = FLASH_ATTR_ERASED_IS_ONE | FLASH_ATTR_MEMORY_MAPPED, .page_size = 8,
    .sectors_count = 256, .sectors = NULL, .sectors_size = 1024, .address = NULL, .size = FLASH_SIZE,
};
msg_t eflStart(EFlashDriver *e, const void *c) { (void)e; (void)c; return HAL_RET_SUCCESS; }
void  eflStop(EFlashDriver *e) { (void)e; }
const flash_descriptor_t *flashGetDescriptor(BaseFlash *f) { (void)f; desc.address = flash; return &desc; }
uint32_t       flashGetSectorSize(BaseFlash *f, flash_sector_t s) { (void)f; (void)s; return 1024; }
flash_offset_t flashGetSectorOffset(BaseFlash *f, flash_sector_t s) { (void)f; return s * 1024u; }
void          *flashGetOffsetAddress(BaseFlash *f, flash_offset_t o) { (void)f; return flash + o; }
flash_error_t  flashStartEraseSector(BaseFlash *f, flash_sector_t s) {
    (void)f;
    memset(flash + s * 1024u, 0xFF, 1024);
    return FLASH_NO_ERROR;
}
flash_error_t flashWaitErase(BaseFlash *f) { (void)f; return FLASH_NO_ERROR; }
flash_error_t flashProgram(BaseFlash *f, flash_offset_t off, size_t n, const uint8_t *pp) {
    (void)f;
    size_t aligned = (n + 7u) & ~(size_t)7u;
    for (size_t i = 0; i < aligned; i += 8) {
        uint8_t line[8];
        memset(line, 0xFF, 8);   /* padded with the erased value */
        memcpy(line, pp + i, (n - i) < 8 ? (n - i) : 8);
        uint64_t existing, want;
        memcpy(&existing, flash + off + i, 8);
        memcpy(&want, line, 8);
        if (existing != UINT64_MAX) return FLASH_ERROR_PROGRAM;   /* hal_efl_lld.c: refuse a line not erased */
        ctl->programs++;
        if (ctl->cut_at && ctl->programs == ctl->cut_at) {
            uint64_t meant_to_clear = ~want;   /* physical 0s = the store's logical 1s */
            uint64_t got            = UINT64_MAX & ~(meant_to_clear & ctl->survive);
            memcpy(flash + off + i, &got, 8);
            ctl->cut_fired = 1;
            fflush(stdout);
            _exit(CUT_EXIT);   /* the reset: nothing after the cut runs */
        }
        memcpy(flash + off + i, &want, 8);
    }
    return FLASH_NO_ERROR;
}
void chSysHalt(const char *r) { fprintf(stderr, "chSysHalt: %s\n", r); abort(); }

/* ---------------- board glue ---------------- */
uint32_t timer_read32(void) { return now_ms; }
bool     sleep_recovering(void) { return false; }
/* quantum/eeconfig.c:332-339: the kb datablock wrappers are these calls. */
bool     eeconfig_is_kb_datablock_valid(void) { return nvm_eeconfig_is_kb_datablock_valid(); }
uint32_t eeconfig_read_kb_datablock(void *d, uint32_t o, uint32_t l) { return nvm_eeconfig_read_kb_datablock(d, o, l); }
uint32_t eeconfig_update_kb_datablock(const void *d, uint32_t o, uint32_t l) { return nvm_eeconfig_update_kb_datablock(d, o, l); }

/* ---------------- sessions ---------------- */
typedef void (*session_fn)(void *);
static int session(session_fn fn, void *arg) {
    fflush(stdout);
    ctl->programs  = 0;
    ctl->cut_fired = 0;
    pid_t p = fork();
    if (p == 0) {
        fn(arg);
        fflush(stdout);
        _exit(0);
    }
    int st = 0;
    waitpid(p, &st, 0);
    return WIFEXITED(st) ? WEXITSTATUS(st) : -1;
}

/* QMK's boot order: eeprom_driver_init() (wear_leveling_init: the consolidated
 * copy, then the log played back), then quantum_init()'s signature check. */
static void boot_and_read(void *unused) {
    (void)unused;
    eeprom_driver_init();
    res->enabled = nvm_eeconfig_is_enabled();
    eeprom_read_block(res->img, (const void *)0, sizeof res->img);
    uint64_t raw;
    memcpy(&raw, flash + (FLASH_SIZE - 2048u) + LOGSTART, 8);
    raw = ~raw;
    memcpy(res->line, &raw, 8);
}

static const rgb_config_t RGB0 = {.enable = 1, .mode = 3, .hsv = {.h = 36, .s = 64, .v = 191}, .speed = 102, .flags = 0xFF};

/* A board as JD's would be: eeconfig_init()'s fields we look at, a lighting
 * config, the kb datablock through kb_eeconfig.c, then a clean log. */
static void provision(void *unused) {
    (void)unused;
    eeprom_driver_init();
    nvm_eeconfig_erase();
    nvm_eeconfig_enable();
    nvm_eeconfig_update_default_layer((layer_state_t)1 << 2);   /* MACBASE, keymap.c:72 */
    keymap_config_t kc = {.raw = 0};
    kc.oneshot_enable     = true;   /* eeconfig_init_quantum()'s defaults */
    kc.autocorrect_enable = true;
    nvm_eeconfig_update_keymap(&kc);
    nvm_eeconfig_update_rgb_matrix(&RGB0);
    kb_eeconfig_init();
    kb_eeconfig_set_bt_profile(CH582_PROFILE_BT_1);   /* 0x31 */
    kb_eeconfig_set_rtc_period(32750);
    kb_eeconfig_set_lcd_brightness(80);
    kb_eeconfig_set_clock_mode(0);
    kb_eeconfig_set_batt_level(1000);
    kb_eeconfig_set_power_mode(1);
    kb_eeconfig_set_ind_level(IND_LOCKS, 30);
    kb_eeconfig_set_ind_level(IND_CHARGING, 60);
    kb_eeconfig_set_batt_view(KB_BATT_VIEW_PERCENT);
    now_ms += 5000;
    kb_eeconfig_task();
    wear_leveling_consolidate();
}

/* The writes the cut lands in, each through the real path. */
static void w_kb_brightness(void *unused) {   /* menu or Fn+PgDn: the backlight 80 -> 40, 5 s later */
    (void)unused;
    eeprom_driver_init();
    kb_eeconfig_init();
    kb_eeconfig_set_lcd_brightness(40);
    now_ms += 5000;
    kb_eeconfig_task();   /* eeprom_update_block(10 B at 37): log lines (37,5) and (42,5) */
}
static void w_rgb_hue(void *unused) {   /* Fn+Right: a hue step, saved 750 ms later */
    (void)unused;
    eeprom_driver_init();
    rgb_config_t r = RGB0;
    r.hsv.h = 40;
    nvm_eeconfig_update_rgb_matrix(&r);   /* 8 B at 23: lines (23,5) and (28,3) */
}
static void w_winmac(void *unused) {   /* the Win/Mac switch to Win: keymap.c:72 */
    (void)unused;
    eeprom_driver_init();
    nvm_eeconfig_update_default_layer((layer_state_t)1 << 0);   /* 1 B at 3: line (3,1) */
}
static void w_prof_magic(void *unused) {   /* profiles.c's first write: the block's magic at PROF_BASE (806) */
    (void)unused;
    eeprom_driver_init();
    uint8_t m = 0xA4;
    wear_leveling_write(806, &m, 1);
}

/* ---------------- harness ---------------- */
static uint8_t provisioned_flash[2048];
static uint8_t provisioned_img[WEAR_LEVELING_LOGICAL_SIZE];
static void restore(void) { memcpy(flash + FLASH_SIZE - 2048u, provisioned_flash, 2048); }

static int run_cut(session_fn w, uint64_t survive) {
    restore();
    ctl->cut_at  = 1;
    ctl->survive = survive;
    int st       = session(w, NULL);
    ctl->cut_at  = 0;
    if (st != CUT_EXIT) {
        printf("  (the cut did not fire: session exit %d)\n", st);
        return 0;
    }
    session(boot_and_read, NULL);
    return 1;
}

/* Outside [lo, hi): bytes that differ from the provisioned image. */
static int damage_outside(unsigned lo, unsigned hi, unsigned *first) {
    int n = 0;
    for (unsigned i = 0; i < WEAR_LEVELING_LOGICAL_SIZE; i++) {
        if (i >= lo && i < hi) continue;
        if (res->img[i] != provisioned_img[i]) {
            if (!n && first) *first = i;
            n++;
        }
    }
    return n;
}
static void show_line(const char *tag) {
    write_log_entry_t e;
    memcpy(e.raw8, res->line, 8);
    printf("  %s: %02X %02X %02X | %02X %02X %02X %02X %02X  -> type %u, address %u, length %u\n", tag, e.raw8[0], e.raw8[1], e.raw8[2],
           e.raw8[3], e.raw8[4], e.raw8[5], e.raw8[6], e.raw8[7], (unsigned)LOG_ENTRY_GET_TYPE(e), (unsigned)LOG_ENTRY_MULTIBYTE_GET_ADDRESS(e),
           (unsigned)LOG_ENTRY_MULTIBYTE_GET_LENGTH(e));
}

/* Enumerate every subset of the header's 1-bits (the data bits kept whole) for
 * one write, and sort the outcomes. */
static int enumerate(const char *name, session_fn w, uint32_t addr, uint8_t len, unsigned lo, unsigned hi) {
    write_log_entry_t e    = LOG_ENTRY_MAKE_MULTIBYTE(addr, len);
    uint32_t          hdr  = (uint32_t)e.raw8[0] | ((uint32_t)e.raw8[1] << 8) | ((uint32_t)e.raw8[2] << 16);
    int               bits[24], nb = 0;
    for (int b = 0; b < 24; b++)
        if (hdr & (1u << b)) bits[nb++] = b;
    int wipe = 0, silent = 0, intended = 0, noop = 0, total = 0;
    for (unsigned s = 0; s < (1u << nb); s++) {
        uint64_t lost = 0;
        for (int k = 0; k < nb; k++)
            if (s & (1u << k)) lost |= 1ull << bits[k];
        if (!run_cut(w, ~lost)) continue;
        total++;
        write_log_entry_t g;
        memcpy(g.raw8, res->line, 8);
        unsigned first = 0;
        if (!res->enabled) {
            wipe++;
        } else if (damage_outside(lo, hi, &first)) {
            silent++;
        } else if (LOG_ENTRY_MULTIBYTE_GET_LENGTH(g) == 0) {
            noop++;
        } else {
            intended++;
        }
    }
    printf("  %s: %d header-bit tear shapes: %d wipe the store (magic broken), %d silently change other settings, %d stay inside the intended bytes, %d replay nothing\n",
           name, total, wipe, silent, intended, noop);
    return total > 0 && wipe == 0 && silent == 0;
}

int main(void) {
    flash = mmap(NULL, FLASH_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    ctl   = mmap(NULL, sizeof *ctl, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    res   = mmap(NULL, sizeof *res, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    if (flash == MAP_FAILED || ctl == MAP_FAILED || res == MAP_FAILED) return 2;
    memset(flash, 0xFF, FLASH_SIZE);
    memset(ctl, 0, sizeof *ctl);

    if (session(provision, NULL) != 0) { puts("provision failed"); return 2; }
    memcpy(provisioned_flash, flash + FLASH_SIZE - 2048u, 2048);
    session(boot_and_read, NULL);
    memcpy(provisioned_img, res->img, sizeof provisioned_img);
    printf("provisioned: magic %02X%02X, default layer %02X, keymap_config %02X%02X, rgb h/s/v/speed %u/%u/%u/%u, kb[0..4] %02X %02X %02X %02X %02X\n",
           res->img[1], res->img[0], res->img[3], res->img[5], res->img[4], res->img[24], res->img[25], res->img[26], res->img[27], res->img[37],
           res->img[38], res->img[39], res->img[40], res->img[41]);
    int ok = 1;

    /* Control: the same write with no cut. */
    restore();
    session(w_kb_brightness, NULL);
    session(boot_and_read, NULL);
    int ctrl_ok = res->enabled && res->img[40] == 41 && damage_outside(37, 47, NULL) == 0;
    printf("control, no cut: enabled %d, kb lcd_brightness_p1 %u (want 41), nothing else changed: %s\n", res->enabled, res->img[40], ctrl_ok ? "yes" : "NO");
    ok &= ctrl_ok;

    /* A: the kb datablock save; address bits 0, 2, 5 and length bit 0 never programmed. */
    puts("\nA. kb datablock save (brightness 80 -> 40), cut in its first line: address 0x25 loses bits 0,2,5; length 5 loses bit 0");
    if (run_cut(w_kb_brightness, ~((1ull << 3) | (0x25ull << 16)))) {
        show_line("torn line as played back");
        printf("  after boot: magic %02X%02X, nvm_eeconfig_is_enabled() = %d\n", res->img[1], res->img[0], res->enabled);
        int a = res->enabled;
        printf("  %s\n", a ? "ok: no wipe" : "FAIL: replayed at address 0; quantum_init() would run eeconfig_init() and wipe the store");
        ok &= a;
    }

    /* B: the same save; address bits 0 and 5 lost (0x25 -> 0x04, keymap_config). */
    puts("\nB. the same save, address bits 0 and 5 lost (0x25 -> 0x04)");
    if (run_cut(w_kb_brightness, ~(0x21ull << 16))) {
        show_line("torn line as played back");
        keymap_config_t kc;
        memcpy(&kc.raw, &res->img[4], 2);
        printf("  after boot: enabled %d, keymap_config %04X (was %02X%02X): swap_control_capslock %d capslock_to_control %d no_gui %d swap_grave_esc %d\n",
               res->enabled, kc.raw, provisioned_img[5], provisioned_img[4], kc.swap_control_capslock, kc.capslock_to_control, kc.no_gui,
               kc.swap_grave_esc);
        unsigned first = 0;
        int      n     = damage_outside(37, 47, &first);
        printf("  bytes changed outside the kb block: %d (first at %u); the kb block itself: lcd_brightness_p1 %u (still the old 81)\n", n, first, res->img[40]);
        int b = res->enabled && n == 0 && kc.raw == (uint16_t)(provisioned_img[4] | provisioned_img[5] << 8);
        printf("  %s\n", b ? "ok: no silent change" : "FAIL: a silent, persistent change outside the kb block");
        ok &= b;
    }

    /* C: RGB save, the line's first word programmed, its second not. */
    puts("\nC. RGB config save (a hue step), cut between the line's two 32-bit words (word 0 programmed, word 1 not)");
    if (run_cut(w_rgb_hue, 0x00000000FFFFFFFFull)) {
        show_line("torn line as played back");
        printf("  after boot: enable|mode %02X, h %u s %u v %u speed %u (were %u %u %u %u)\n", res->img[23], res->img[24], res->img[25], res->img[26],
               res->img[27], RGB0.hsv.h, RGB0.hsv.s, RGB0.hsv.v, RGB0.speed);
        int c = res->enabled && res->img[24] == RGB0.hsv.h && res->img[25] == RGB0.hsv.s && res->img[26] == RGB0.hsv.v &&
                res->img[27] == RGB0.speed;
        printf("  %s\n", c ? "ok: the old lighting kept" : "FAIL: the torn line changed the lighting");
        ok &= c;
    }

    /* Exhaustive over the header bits (data kept whole). */
    puts("\nD. every tear shape of the header's 1-bits, data bits kept:");
    ok &= enumerate("kb datablock line (37,4)", w_kb_brightness, 37, 4, 37, 47);
    ok &= enumerate("default layer at a Win/Mac flip (3,1)", w_winmac, 3, 1, 3, 4);
    ok &= enumerate("RGB config line (23,4)", w_rgb_hue, 23, 4, 23, 31);
    ok &= enumerate("profiles' magic byte (806,1)", w_prof_magic, 806, 1, 806, 807);

    printf("\n%s\n", ok ? "RESULT: PASS (no tear wipes the store or changes another setting)" : "RESULT: FAIL");
    return ok ? 0 : 1;
}
