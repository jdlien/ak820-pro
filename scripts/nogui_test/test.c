/* The Win/Mac switch's GUI lock (the 10-31 audit, F-029; first written as its
 * verify-029): the Mac side clears keymap_config.no_gui in RAM only, and the
 * Windows side took nothing back, so after Windows, Mac, Windows a reboot
 * relocked the Win key and the next Fn+Left GUI seemed to do nothing. Passes
 * when a reboot keeps the visible lock and each press flips it.
 *
 * Compiles, unedited and by path:
 *   keyboards/a_jazz/ak820pro/keymaps/via/keymap.c   (dip_switch_update_user, keymaps[])
 *   quantum/process_keycode/process_magic.c           (GU_TOGG: read EE, toggle, write EE)
 *   quantum/keycode_config.c                          (KC_LGUI -> KC_NO while no_gui)
 *   quantum/dip_switch.c                              (dip_switch_init's forced read, dip_switch_task)
 * with a fake EEPROM for the keymap config and a fake pin table for the switch.
 *
 * boot() models quantum/keyboard.c: quantum_init()'s eeconfig_read_keymap
 * (keyboard.c:441), then keyboard_init()'s dip_switch_init() (keyboard.c:520).
 * dip_switch_update_kb() mirrors ak820pro.c:119-133: the keymap's hook first,
 * then the logo and prof_switch(), neither of which touches keymap_config. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kb_stub.h"
#include "ak820pro.h"   /* the real one: WINBASE..MACFN */
#include "eeconfig.h"

bool fake_pin_level[64];
static uint16_t fake_ee_keymap;          /* EECONFIG_KEYMAP */
static uint8_t  fake_ee_default_layer;   /* EECONFIG_DEFAULT_LAYER (index) */
static unsigned ee_keymap_writes, prof_switch_calls;
extern const uint16_t keymaps[][MATRIX_ROWS][MATRIX_COLS];

/* ---- stubs ---- */
void eeconfig_read_keymap(keymap_config_t *kc) { kc->raw = fake_ee_keymap; }
void eeconfig_update_keymap(const keymap_config_t *kc) { fake_ee_keymap = kc->raw; ee_keymap_writes++; }
void clear_keyboard(void) {}
void eeconfig_update_handedness(bool val) { (void)val; }
void host_consumer_send(uint16_t usage) { (void)usage; }
void set_single_persistent_default_layer(uint8_t l) { fake_ee_default_layer = l; }

/* ak820pro.c's dip_switch_update_kb, keymap_config-relevant part verbatim:
 * the user hook first; the rest (display_draw_*_logo, prof_switch,
 * bt_ui_mode_slider) never reads or writes keymap_config (grep). */
bool dip_switch_update_kb(uint8_t index, bool active) {
    if (!dip_switch_update_user(index, active)) return false;
    if (index == 0) prof_switch_calls++;
    return true;
}

/* B1 = index 0 (Win when low: dip_switch_state = !gpio_read_pin). */
#define PIN_OS 1
static void set_switch(bool windows) { fake_pin_level[PIN_OS] = !windows; }

static void boot(void) {
    keymap_config.raw = 0xA5A5;            /* RAM is lost at a brownout */
    eeconfig_read_keymap(&keymap_config);  /* keyboard.c:441 */
    dip_switch_init();                     /* keyboard.c:520: forced read */
}
static void flip(bool windows) { set_switch(windows); dip_switch_task(); }

static void press(uint16_t kc) {
    keyrecord_t r; memset(&r, 0, sizeof r);
    r.event.pressed = true;
    if (process_magic(kc, &r)) { /* not magic */ }
}

static bool win_key_works(void) { return keycode_config(KC_LEFT_GUI) == KC_LEFT_GUI; }
static void show(const char *what) {
    printf("%-52s RAM no_gui=%d  EE no_gui=%d  Win key %s  (LED %s)\n", what,
           keymap_config.no_gui, ((keymap_config_t){.raw = fake_ee_keymap}).no_gui,
           win_key_works() ? "works " : "LOCKED", keymap_config.no_gui ? "on" : "off");
}

static int fails;
#define CHECK(c, msg) do { if (!(c)) { printf("  FAIL: %s\n", msg); fails++; } else printf("  ok:   %s\n", msg); } while (0)

int main(void) {
    /* The real keymap: GU_TOGG is Fn+LGui on WINFN only (bottom row, 2nd key). */
    const unsigned GUI_POS = 15 + 15 + 15 + 14 + 13 + 1;
    uint16_t win_fn_lgui = keymaps[WINFN][0][GUI_POS];
    uint16_t mac_fn_lgui = keymaps[MACFN][0][GUI_POS];
    printf("keymaps[WINFN] bottom-row key 2 = 0x%04X (GU_TOGG = 0x%04X); keymaps[MACFN] = 0x%04X\n",
           win_fn_lgui, GU_TOGG, mac_fn_lgui);
    CHECK(win_fn_lgui == GU_TOGG, "Fn+LGui on WINFN is GU_TOGG in the real keymap");
    CHECK(keymaps[WINBASE][0][GUI_POS] == KC_LGUI, "the key under it on WINBASE is KC_LGUI");

    /* Factory state: eeconfig_init_quantum leaves no_gui false. */
    fake_ee_keymap = 0;
    set_switch(true);
    fake_pin_level[12] = fake_pin_level[13] = true;
    boot();                                      show("1. boot on Windows");
    CHECK(win_key_works(), "Win key works after a clean boot");

    press(win_fn_lgui);                          show("2. Fn+LGui (GU_TOGG): lock");
    CHECK(!win_key_works() && keymap_config.no_gui, "locked in RAM");
    CHECK(((keymap_config_t){.raw = fake_ee_keymap}).no_gui, "locked in EEPROM (persisted)");

    flip(false);                                 show("3. switch to Mac");
    CHECK(fake_ee_default_layer == MACBASE, "default layer is MACBASE");
    flip(true);                                  show("4. switch back to Windows");
    bool step4_works = win_key_works();
    bool ram_ee_agree = keymap_config.no_gui == ((keymap_config_t){.raw = fake_ee_keymap}).no_gui;
    printf("  RAM and EEPROM %s\n", ram_ee_agree ? "agree" : "DISAGREE (no write on the flip)");

    /* Symptom A: a reboot on the Windows side locks the Win key again. */
    keymap_config_t saved_ram = keymap_config; uint16_t saved_ee = fake_ee_keymap;
    boot();                                      show("5. brownout/reboot, switch still on Windows");
    bool relocked = step4_works && !win_key_works();
    bool reboot_keeps = (step4_works == win_key_works());
    printf("  %s\n", relocked ? "BUG (symptom A): the Win key is locked again after the reboot"
                              : "no bug: the reboot changed nothing visible");

    /* Symptom B: from step 4's state, one GU_TOGG press does nothing visible,
     * because process_magic reloads no_gui from EEPROM (true) before toggling. */
    keymap_config = saved_ram; fake_ee_keymap = saved_ee;
    show("6. (back to step 4's state)");
    bool before = win_key_works();
    press(win_fn_lgui);                          show("7. Fn+LGui once, wanting to lock");
    bool first_press_noop = before && win_key_works();
    bool press_flips = (before != win_key_works());
    printf("  %s\n", first_press_noop ? "BUG (symptom B): the first press leaves the Win key unlocked"
                                      : "no bug: the press flipped the visible lock");
    press(win_fn_lgui);                          show("8. Fn+LGui again");

    /* Control: unlocking with GU_TOGG before flipping leaves nothing behind. */
    fake_ee_keymap = 0; set_switch(true); boot();
    press(win_fn_lgui); press(win_fn_lgui); flip(false); flip(true); boot();
    show("9. control: lock, unlock, Mac, Win, reboot");
    CHECK(win_key_works(), "control: Win key works (no stale EEPROM bit)");

    printf("\nprof_switch calls=%u, EE keymap writes=%u\n", prof_switch_calls, ee_keymap_writes);
    printf("invariant: a reboot keeps the visible Win lock:        %s\n", reboot_keeps ? "holds" : "VIOLATED");
    printf("invariant: each GU_TOGG press flips the visible lock:  %s\n", press_flips ? "holds" : "VIOLATED");
    bool ok = !fails && !relocked && !first_press_noop && reboot_keeps && press_flips;
    printf("RESULT: %s\n", fails ? "TEST SETUP FAILURE" : ok ? "PASS (the invariants hold)" :
                           relocked && first_press_noop ? "FAIL (the bug: relocked at the reboot)" : "FAIL");
    return fails ? 2 : ok ? 0 : 1;
}
