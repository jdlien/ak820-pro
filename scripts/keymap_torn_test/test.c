/* A VIA key assignment, an encoder's and a keymap restore's keycodes are each
 * one emulated-EEPROM write, so a power cut leaves every key old or new
 * (plans/AUDIT-2026-10-31.md, F-017; first written as the audit's verify-038).
 * Before the fix each was two byte writes, and a cut between them stored the
 * new high byte with the old low one: a third keycode.
 *
 * Compiles the REAL upstream files from the firmware tree (by path, unedited):
 *   quantum/nvm/eeprom/nvm_dynamic_keymap.c   (#included below so the fix
 *                                              variant can reuse its static
 *                                              address helper)
 *   drivers/eeprom/eeprom_driver.c            (eeprom_update_byte/_block)
 *   drivers/eeprom/eeprom_wear_leveling.c     (eeprom_write_block -> wear_leveling_write)
 *   quantum/wear_leveling/wear_leveling.c     (the write log + playback at boot)
 *   lib/fnv/hash_64a.c
 * over a fake of the SN32F290 EFL backing store as wear_leveling_efl.c drives
 * it: 8-byte lines, erased 0xFF, values stored complemented, a program refused
 * over a line that is not erased.
 *
 * The power cut is CLEAN: it stops the backing store at the Nth program/erase
 * (op N and every later op fail; no partially programmed line). That is the
 * most charitable model of the flash: a torn line program would only add
 * failure modes. "Boot" re-runs wear_leveling_init(), which rebuilds the
 * cache from flash only (the RAM cache is lost at power-off). */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

#include "nvm_dynamic_keymap.c"   /* the real one: run.sh puts its directory on the path */
#include "wear_leveling.h"
#include "wear_leveling_internal.h"

/* ---- fake EFL backing store ------------------------------------------- */
static uint8_t flash[WEAR_LEVELING_BACKING_SIZE];
static int     ops, cut_at = -1;
static bool    dead;
static int     sessions; /* eeprom_write_block calls (the board's flash_stats "sessions") */

static bool op_allowed(void) {
    if (dead) return false;
    if (cut_at >= 0 && ops == cut_at) { dead = true; return false; }
    ops++;
    return true;
}
bool backing_store_init(void) { return true; }
bool backing_store_unlock(void) { return !dead; }
bool backing_store_lock(void) { return true; }
bool backing_store_erase(void) {
    if (!op_allowed()) return false;
    memset(flash, 0xFF, sizeof flash);
    return true;
}
bool backing_store_write(uint32_t a, backing_store_int_t v) {
    uint64_t raw;
    memcpy(&raw, &flash[a], 8);
    if (raw != UINT64_MAX) return false; /* the EFL refuses a line not erased */
    if (!op_allowed()) return false;
    raw = ~v;
    memcpy(&flash[a], &raw, 8);
    return true;
}
bool backing_store_read(uint32_t a, backing_store_int_t *v) {
    uint64_t raw;
    memcpy(&raw, &flash[a], 8);
    *v = ~raw;
    return true;
}
/* Strong override of eeprom_wear_leveling.c's weak hook: count sessions. */
void eeprom_wear_leveling_write_hook(uint32_t addr, const void *buf, size_t len) {
    (void)addr; (void)buf; (void)len;
    sessions++;
}

static void power_on(void) { dead = false; cut_at = -1; ops = 0; wear_leveling_init(); }
static void arm_cut(int n) { cut_at = n; ops = 0; dead = false; }

/* ---- keycode names ------------------------------------------------------ */
#define K_LCTL(kc) (0x0100 | (kc))
#define K_MO(l)    (QK_MOMENTARY | (l))
#define K_TO(l)    (QK_TO | (l))
static const char *kc_name(uint16_t kc) {
    static char ring[4][64];
    static int  slot;
    char *b = ring[slot++ & 3];
    if (kc >= QK_TO && kc <= QK_TO_MAX)                snprintf(b, 64, "TO(%u)", kc & 0x1F);
    else if (kc >= QK_MOMENTARY && kc <= QK_MOMENTARY_MAX) snprintf(b, 64, "MO(%u)", kc & 0x1F);
    else if (kc == KC_A) snprintf(b, 64, "KC_A");
    else if (kc == KC_B) snprintf(b, 64, "KC_B");
    else if (kc == KC_C) snprintf(b, 64, "KC_C");
    else if (kc == KC_4) snprintf(b, 64, "KC_4");
    else if (kc == KC_VOLU) snprintf(b, 64, "KC_VOLU");
    else if (kc == KC_EQUAL) snprintf(b, 64, "KC_EQL");
    else if (kc == K_LCTL(KC_A)) snprintf(b, 64, "LCTL(KC_A)");
    else if (kc == K_LCTL(KC_C)) snprintf(b, 64, "LCTL(KC_C)");
    else if (kc == K_LCTL(KC_EQUAL)) snprintf(b, 64, "LCTL(KC_EQL)");
    else if (kc == K_LCTL(KC_VOLU)) snprintf(b, 64, "LCTL(KC_VOLU)");
    else snprintf(b, 64, "0x%04X", kc);
    return b;
}

/* ---- the fix sketch: one 2-byte block, so one multibyte log line --------- */
static void fixed_update_keycode(uint8_t layer, uint8_t row, uint8_t column, uint16_t keycode) {
    if (layer >= DYNAMIC_KEYMAP_LAYER_COUNT || row >= MATRIX_ROWS || column >= MATRIX_COLS) return;
    uint8_t be[2] = {(uint8_t)(keycode >> 8), (uint8_t)(keycode & 0xFF)};
    eeprom_update_block(be, dynamic_keymap_key_to_eeprom_address(layer, row, column), 2);
}

typedef void (*setter_t)(uint8_t, uint8_t, uint8_t, uint16_t);

static int failures;

/* Fresh store holding `from` at (L,R,C), consolidated (log empty). */
static void fresh_store(uint8_t L, uint8_t R, uint8_t C, uint16_t from) {
    memset(flash, 0xFF, sizeof flash);
    power_on();
    wear_leveling_erase();
    nvm_dynamic_keymap_update_keycode(L, R, C, from);
    wear_leveling_consolidate();
    power_on();
}

/* Sweep the cut over every op of one key assignment; report what boots. */
static int sweep(const char *label, setter_t set, uint8_t L, uint8_t R, uint8_t C, uint16_t from, uint16_t to) {
    int torn = 0;
    /* How many ops the uncut assignment takes, and how many sessions. */
    fresh_store(L, R, C, from);
    sessions = 0; arm_cut(-1);
    set(L, R, C, to);
    int total = ops, sess = sessions;
    printf("  %s: %s -> %s: %d write session(s), %d line program(s)\n", label, kc_name(from), kc_name(to), sess, total);
    for (int n = 0; n <= total; n++) {
        fresh_store(L, R, C, from);
        arm_cut(n);
        set(L, R, C, to);
        power_on(); /* reboot from flash only */
        uint16_t got = nvm_dynamic_keymap_read_keycode(L, R, C);
        const char *what = got == from ? "old (fine)" : got == to ? "new (fine)" : "THIRD KEYCODE";
        if (got != from && got != to) torn++;
        printf("    cut before op %d -> boots with 0x%04X %-14s %s\n", n, got, kc_name(got), what);
    }
    return torn;
}

int main(void) {
    printf("layout: DYNAMIC_KEYMAP_EEPROM_ADDR=%d, layers=%d, %dx%d, encoder map at %d, macros at %d (+%d)\n",
           (int)DYNAMIC_KEYMAP_EEPROM_ADDR, DYNAMIC_KEYMAP_LAYER_COUNT, MATRIX_ROWS, MATRIX_COLS,
           (int)DYNAMIC_KEYMAP_ENCODER_EEPROM_ADDR, (int)DYNAMIC_KEYMAP_MACRO_EEPROM_ADDR, DYNAMIC_KEYMAP_MACRO_EEPROM_SIZE);

    /* 1. The finding's example, through the real upstream setter. */
    printf("\n[1] nvm_dynamic_keymap_update_keycode (VIA id_dynamic_keymap_set_keycode), layer 0 row 3 col 1\n");
    int t1 = sweep("upstream", nvm_dynamic_keymap_update_keycode, 0, 3, 1, KC_A, K_MO(1));
    int t2 = sweep("upstream", nvm_dynamic_keymap_update_keycode, 0, 3, 1, KC_A, K_LCTL(KC_C));
    int t3 = sweep("upstream", nvm_dynamic_keymap_update_keycode, 1, 0, 0, K_MO(1), KC_B);
    if (t1 || t2 || t3) { printf("  FAIL a torn keycode\n"); failures++; }

    /* 2. The encoder map: the same two sessions. */
    printf("\n[2] nvm_dynamic_keymap_update_encoder (VIA id_dynamic_keymap_set_encoder), layer 0 enc 0 cw\n");
    {
        memset(flash, 0xFF, sizeof flash);
        power_on(); wear_leveling_erase();
        nvm_dynamic_keymap_update_encoder(0, 0, true, KC_VOLU);
        wear_leveling_consolidate(); power_on();
        sessions = 0; arm_cut(-1);
        nvm_dynamic_keymap_update_encoder(0, 0, true, K_LCTL(KC_EQUAL));
        int total = ops, sess = sessions;
        int torn = 0;
        for (int n = 0; n <= total; n++) {
            memset(flash, 0xFF, sizeof flash);
            power_on(); wear_leveling_erase();
            nvm_dynamic_keymap_update_encoder(0, 0, true, KC_VOLU);
            wear_leveling_consolidate(); power_on();
            arm_cut(n);
            nvm_dynamic_keymap_update_encoder(0, 0, true, K_LCTL(KC_EQUAL));
            power_on();
            uint16_t got = nvm_dynamic_keymap_read_encoder(0, 0, true);
            bool third = got != KC_VOLU && got != K_LCTL(KC_EQUAL);
            torn += third;
            printf("    %d session(s); cut before op %d -> boots with 0x%04X %-14s %s\n", sess, n, got, kc_name(got), third ? "THIRD KEYCODE" : "fine");
        }
        if (torn) { printf("  FAIL a torn encoder keycode\n"); failures++; }
    }

    /* 3. The keymap restore (VIA id_dynamic_keymap_set_buffer, ak820keymap.py
     *    restore via flash.sh): byte by byte. A 28-byte packet changing 14
     *    keycodes from KC_A to MO(1); cut after 2k+1 programs leaves the
     *    (k+1)th keycode torn. */
    printf("\n[3] nvm_dynamic_keymap_update_buffer (VIA id_dynamic_keymap_set_buffer), 28-byte packet\n");
    {
        uint8_t pkt[28];
        for (int i = 0; i < 14; i++) { pkt[2 * i] = (uint8_t)(K_MO(1) >> 8); pkt[2 * i + 1] = (uint8_t)(K_MO(1) & 0xFF); }
        int torn_cuts = 0;
        for (int n = 0; n <= 28; n++) {
            memset(flash, 0xFF, sizeof flash);
            power_on(); wear_leveling_erase();
            for (int c = 0; c < 14; c++) nvm_dynamic_keymap_update_keycode(0, 0, c, KC_A);
            wear_leveling_consolidate(); power_on();
            sessions = 0; arm_cut(n);
            nvm_dynamic_keymap_update_buffer(0, sizeof pkt, pkt);
            power_on();
            int third = 0;
            for (int c = 0; c < 14; c++) {
                uint16_t got = nvm_dynamic_keymap_read_keycode(0, 0, c);
                if (got != KC_A && got != K_MO(1)) { third++; if (n == 3) printf("    cut before op 3: key (0,0,%d) boots as %s\n", c, kc_name(got)); }
            }
            torn_cuts += third > 0;
        }
        printf("    %d of 29 cut points leave a third keycode\n", torn_cuts);
        if (torn_cuts) { printf("  FAIL torn keycodes in the buffer restore\n"); failures++; }
    }

    /* 4. The window includes a consolidation: the first byte's line fills the
     *    log, so the whole store is erased and rewritten (with new-high/old-low
     *    in the cache) before the second byte is written. */
    printf("\n[4] the high byte's line is the log's last: consolidation inside the window\n");
    {
        memset(flash, 0xFF, sizeof flash);
        power_on(); wear_leveling_erase();
        nvm_dynamic_keymap_update_keycode(0, 3, 1, KC_A);
        wear_leveling_consolidate(); power_on();
        /* Fill the log to one line short of full with unrelated macro-buffer writes. */
        uint8_t v = 0;
        uint32_t cap = WEAR_LEVELING_BACKING_SIZE - (WEAR_LEVELING_LOGICAL_SIZE + 8);
        while (wear_leveling_log_used() < cap - 8) { v++; nvm_dynamic_keymap_macro_update_buffer(0, 1, &v); }
        printf("    log used %u of %u bytes before the assignment\n", (unsigned)wear_leveling_log_used(), (unsigned)cap);
        /* Snapshot so each cut starts from the same flash. */
        static uint8_t snap[WEAR_LEVELING_BACKING_SIZE];
        memcpy(snap, flash, sizeof flash);
        power_on(); arm_cut(-1);
        nvm_dynamic_keymap_update_keycode(0, 3, 1, K_MO(1));
        int total = ops;
        printf("    the assignment takes %d ops (1 log line, 1 erase, %d consolidated lines + hash, 1 log line)\n", total, WEAR_LEVELING_LOGICAL_SIZE / 8);
        int torn = 0, wiped = 0, other = 0;
        char torn_ops[256] = "";
        for (int n = 0; n <= total; n++) {
            memcpy(flash, snap, sizeof flash);
            power_on(); arm_cut(n);
            nvm_dynamic_keymap_update_keycode(0, 3, 1, K_MO(1));
            power_on();
            uint16_t got = nvm_dynamic_keymap_read_keycode(0, 3, 1);
            if (got == (uint16_t)((K_MO(1) & 0xFF00) | (KC_A & 0x00FF))) {
                torn++;
                char t[16]; snprintf(t, sizeof t, " %d", n); strncat(torn_ops, t, sizeof torn_ops - strlen(torn_ops) - 1);
            } else if (got == 0x0000) wiped++;   /* the consolidation's erase-then-rewrite lost the store (leds.md documents it) */
            else if (got != KC_A && got != K_MO(1)) other++;
        }
        printf("    cuts booting the torn %s: %d (before op%s)\n", kc_name((K_MO(1) & 0xFF00) | (KC_A & 0x00FF)), torn, torn_ops);
        printf("    cuts inside the consolidation booting an empty store (KC_NO; the documented erase-then-rewrite loss): %d\n", wiped);
        if (other || torn) { printf("    FAIL other outcomes: %d, torn %d\n", other, torn); failures++; }
    }

    /* 5. The fix sketch: one eeprom_update_block of the two big-endian bytes. */
    printf("\n[5] fix sketch: eeprom_update_block(be, addr, 2) -- one session, one line\n");
    int f1 = sweep("fixed", fixed_update_keycode, 0, 3, 1, KC_A, K_MO(1));
    int f2 = sweep("fixed", fixed_update_keycode, 0, 3, 1, KC_A, K_LCTL(KC_C));
    int f3 = sweep("fixed", fixed_update_keycode, 1, 0, 0, K_MO(1), KC_B);
    if (f1 || f2 || f3) { printf("  the fix still tears\n"); failures++; }
    /* and the fixed setter reads back identically to the upstream one */
    fresh_store(0, 3, 1, KC_A);
    fixed_update_keycode(0, 3, 1, K_MO(1));
    power_on();
    if (nvm_dynamic_keymap_read_keycode(0, 3, 1) != K_MO(1)) { printf("  fixed setter wrote the wrong bytes\n"); failures++; }

    printf("\nRESULT: %s\n", failures ? "FAIL" : "PASS (every cut leaves each keycode old or new)");
    return failures ? 1 : 0;
}
