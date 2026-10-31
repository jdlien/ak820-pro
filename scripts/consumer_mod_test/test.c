/* The knob's modified-consumer burst never releases a modifier a key holds,
 * and puts back one a key released mid-spin (plans/AUDIT-2026-10-31.md, F-004;
 * first written as the audit's verify-004).
 *
 * What is real here: consumer_mod.c (compiled by path, unedited), QMK's
 * quantum/action_util.c (add_mods/del_mods/get_mods/send_keyboard_report and
 * the report's mods byte) and tmk_core/protocol/report.c, plus register_code,
 * unregister_code, register_mods, unregister_mods and extract_mod_bits cut
 * verbatim out of quantum/action.c and quantum/quantum.c by build.sh.
 *
 * What is modelled:
 *  - the host: it applies each keyboard report as it arrives, and a consumer
 *    usage is interpreted with the modifiers of the last keyboard report
 *    (that is exactly what the 8 ms gap in process_modified_consumer buys);
 *  - the main loop: 1 ms steps, the 10 Hz housekeeping calling
 *    modified_consumer_task() as ak820pro.c's housekeeping block does
 *    (`if (timer_elapsed32(last_t) >= 100)`);
 *  - a knob detent: encoder.c's encoder-map path, press, wait_ms(
 *    ENCODER_MAP_KEY_DELAY), release, wait_ms(ENCODER_MAP_KEY_DELAY), with the
 *    keycode reaching process_record_kb -> process_modified_consumer;
 *  - a physical modifier or letter key: the plain KC_* action path,
 *    keycode_config() (the real quantum/keycode_config.c, MAGIC_ENABLE) then
 *    process_action's ACT_LMODS with no mods -> register_code() /
 *    unregister_code() (the real functions);
 *  - the keyboard endpoint's delivery: at once, or kb_latency_ms late while
 *    the consumer usage goes at once (the two endpoints are polled
 *    independently, which is what the gap exists to beat).
 */
#include <stdio.h>
#include <string.h>
#include "quantum.h"
#include "host.h"
#include "report.h"
#include "keycode_config.h"
#include "debug.h"
#include "consumer_mod.h"

/* ---- stubs QMK's real files need on the host ---------------------------- */
debug_config_t  debug_config;   /* keymap_config is keycode_config.c's */

static uint32_t now_ms;
uint16_t timer_read(void) { return (uint16_t)now_ms; }
uint32_t timer_read32(void) { return now_ms; }
uint16_t timer_elapsed(uint16_t last) { return (uint16_t)((uint16_t)now_ms - last); }
uint32_t timer_elapsed32(uint32_t last) { return now_ms - last; }
void     wait_ms(uint32_t ms) { now_ms += ms; } /* blocking: no tasks run */
void     register_mouse(uint8_t c, bool p) { (void)c; (void)p; }
/* oneshot-layer helpers in action_util.c reference these; never reached here */
void     layer_on(uint8_t l) { (void)l; }
void     layer_off(uint8_t l) { (void)l; }
void     eeconfig_update_keymap(const keymap_config_t *k) { (void)k; }

/* ---- the host model ----------------------------------------------------- */
static uint8_t host_mods;           /* what the host believes is held */
static uint32_t kb_latency_ms;      /* the keyboard endpoint's delivery delay */
static struct { uint32_t due; uint8_t mods; } kbq[64];
static int kbq_n;
static void host_deliver(void) {    /* the keyboard reports due by now, in order */
    int i = 0;
    while (i < kbq_n && kbq[i].due <= now_ms) host_mods = kbq[i++].mods;
    memmove(kbq, kbq + i, (size_t)(kbq_n - i) * sizeof kbq[0]);
    kbq_n -= i;
}
static void host_mods_arrive(uint8_t m) {
    if (!kb_latency_ms && !kbq_n) { host_mods = m; return; }
    if (kbq_n < 64) { kbq[kbq_n].due = now_ms + kb_latency_ms; kbq[kbq_n].mods = m; kbq_n++; }
}
static uint8_t host_keys[32];       /* 6KRO keys or NKRO bitmap, copied */
static bool    verbose;

static const char *mods_str(uint8_t m) {
    static char bufs[2][64];   /* two per printf */
    static int  n;
    char *b = bufs[n++ & 1];
    b[0] = 0;
    if (!m) return "none";
    if (m & MOD_BIT(KC_LEFT_CTRL)) strcat(b, "LCtl ");
    if (m & MOD_BIT(KC_LEFT_SHIFT)) strcat(b, "LSft ");
    if (m & MOD_BIT(KC_LEFT_ALT)) strcat(b, "LAlt ");
    if (m & MOD_BIT(KC_LEFT_GUI)) strcat(b, "LGui ");
    if (m & MOD_BIT(KC_RIGHT_SHIFT)) strcat(b, "RSft ");
    if (m & MOD_BIT(KC_RIGHT_ALT)) strcat(b, "RAlt ");
    b[strlen(b) - 1] = 0;
    return b;
}

void host_keyboard_send(report_keyboard_t *r) {
    if (verbose && r->mods != host_mods)
        printf("    t=%4u ms  host <- keyboard report, mods %-14s (0x%02x)\n", (unsigned)now_ms, mods_str(r->mods), r->mods);
    host_mods_arrive(r->mods);
    memset(host_keys, 0, sizeof host_keys);
    memcpy(host_keys, r->keys, sizeof r->keys);
}
#ifdef NKRO_ENABLE
bool host_can_send_nkro(void) { return true; }
void host_nkro_send(report_nkro_t *r) {
    if (verbose && r->mods != host_mods)
        printf("    t=%4u ms  host <- NKRO report, mods %-14s (0x%02x)\n", (unsigned)now_ms, mods_str(r->mods), r->mods);
    host_mods_arrive(r->mods);
    memset(host_keys, 0, sizeof host_keys);
    memcpy(host_keys, r->bits, sizeof r->bits < sizeof host_keys ? sizeof r->bits : sizeof host_keys);
}
#endif
static int consumer_events, consumer_alt_only, consumer_full_lsa;
void host_consumer_send(uint16_t usage) {
    if (!usage) return;
    host_deliver();
    consumer_events++;
    uint8_t lsa = MOD_BIT(KC_LEFT_SHIFT) | MOD_BIT(KC_LEFT_ALT);
    if ((host_mods & lsa) == lsa) consumer_full_lsa++;
    else if (host_mods & MOD_BIT(KC_LEFT_ALT)) consumer_alt_only++;
    if (verbose)
        printf("    t=%4u ms  host <- consumer 0x%03x with mods %s%s\n", (unsigned)now_ms, usage, mods_str(host_mods),
               (host_mods & lsa) == MOD_BIT(KC_LEFT_ALT) ? "   <-- Alt+Volume: macOS opens Sound settings" : "");
}
void host_system_send(uint16_t u) { (void)u; }

/* ---- the board's main loop and inputs ----------------------------------- */
static uint32_t hk_last;
static void run_ms(uint32_t n) {
    while (n--) {
        now_ms++;
        host_deliver();
        if (now_ms - hk_last >= 100) {  /* ak820pro.c: the 10 Hz housekeeping */
            hk_last = now_ms;
            modified_consumer_task();
        }
    }
}
static uint8_t phys_mods;            /* the modifiers the keys hold, after keycode_config() */
static void phys_key(uint8_t code, bool down) {
    uint8_t eff = (uint8_t)keycode_config(code);   /* keymap_common.c's action path */
    if (verbose)
        printf("    t=%4u ms  user %s %s\n", (unsigned)now_ms, down ? "presses" : "releases",
               code == KC_LEFT_SHIFT ? "Left Shift" : code == KC_LEFT_ALT ? "Left Option" :
               code == KC_RIGHT_SHIFT ? "Right Shift" : "a letter key");
    if (IS_MODIFIER_KEYCODE(eff)) {
        if (down) phys_mods |= MOD_BIT(eff); else phys_mods &= (uint8_t)~MOD_BIT(eff);
    }
    {   /* the tracker, as process_record_kb calls it */
        keyrecord_t r;
        memset(&r, 0, sizeof r);
        r.event.pressed = down;
        consumer_mod_note_key(code, &r);
    }
    if (down) register_code(eff); else unregister_code(eff);
}
static void detent(uint16_t kc) {
    if (verbose) printf("    t=%4u ms  knob detent\n", (unsigned)now_ms);
    keyrecord_t rec;
    memset(&rec, 0, sizeof rec);
    rec.event.pressed = true;
    if (process_modified_consumer(kc, &rec)) printf("BUG IN HARNESS: keycode not handled\n");
    wait_ms(ENCODER_MAP_KEY_DELAY);
    rec.event.pressed = false;
    process_modified_consumer(kc, &rec);
    wait_ms(ENCODER_MAP_KEY_DELAY);
}

/* Reset everything between scenarios: settle the board's burst, then zero. */
static void reset_world(void) {
    run_ms(1000);
    clear_mods();
    clear_weak_mods();
    clear_keys();
    send_keyboard_report();
    phys_mods = 0;
    consumer_events = consumer_alt_only = consumer_full_lsa = 0;
}

static int fails;
static void check(const char *what, uint8_t got, uint8_t want) {
    bool ok = got == want;
    if (kbq_n) { printf("BUG IN HARNESS: a check with keyboard reports in flight\n"); fails++; }
    printf("  %s %s: host mods %s (0x%02x), physically held %s (0x%02x)\n", ok ? "ok  " : "FAIL", what, mods_str(got), got,
           mods_str(want), want);
    if (!ok) fails++;
}

int main(int argc, char **argv) {
    verbose = argc > 1 && !strcmp(argv[1], "-v");
    const uint16_t VOLU = LSA(KC_AUDIO_VOL_UP);   /* keymap.c MACBASE's CW */
    printf("consumer_mod.c with GAP=%d ms HOLD=%d ms, housekeeping 10 Hz, key delay %d ms%s\n", MODIFIED_CONSUMER_GAP_MS,
           MODIFIED_CONSUMER_HOLD_MS, ENCODER_MAP_KEY_DELAY,
#ifdef NKRO_ENABLE
           ", NKRO reports"
#else
           ", 6KRO reports"
#endif
    );
#ifdef NKRO_ENABLE
    keymap_config.nkro = 1;
#endif
    run_ms(1000);

    printf("\nControl 0: one detent, no keys touched: the burst's mods come and go\n");
    reset_world();
    detent(VOLU);
    run_ms(500);
    check("0.5 s after the detent", host_mods, phys_mods);
    printf("  consumer usages %d, all with Shift+Alt: %s\n", consumer_events, consumer_full_lsa == consumer_events ? "yes" : "NO");

    printf("\nA1: detent, Left Shift pressed 50 ms later and held, a letter typed 400 ms after the detent\n");
    reset_world();
    detent(VOLU);
    run_ms(50);
    phys_key(KC_LEFT_SHIFT, true);
    run_ms(350);
    check("Shift still down, before the letter", host_mods, phys_mods);
    phys_key(KC_H, true);
    check("the letter's report (capital H expected)", host_mods, phys_mods);
    phys_key(KC_H, false);
    phys_key(KC_LEFT_SHIFT, false);
    run_ms(10);

    printf("\nA2: Left Shift held FIRST, then one detent, then 0.5 s, then a letter\n");
    reset_world();
    phys_key(KC_LEFT_SHIFT, true);
    run_ms(200);
    detent(VOLU);
    run_ms(500);
    phys_key(KC_H, true);
    check("the letter's report (capital H expected)", host_mods, phys_mods);
    phys_key(KC_H, false);
    phys_key(KC_LEFT_SHIFT, false);

    printf("\nA3: Left Option held (an Option-click or an app chord), one detent, 0.5 s later\n");
    reset_world();
    phys_key(KC_LEFT_ALT, true);
    run_ms(200);
    detent(VOLU);
    run_ms(500);
    check("Option still physically down", host_mods, phys_mods);
    phys_key(KC_LEFT_ALT, false);

    printf("\nControl R: Right Shift held, one detent, 0.5 s later (RSft is not in LSA's bits)\n");
    reset_world();
    phys_key(KC_RIGHT_SHIFT, true);
    run_ms(200);
    detent(VOLU);
    run_ms(500);
    check("Right Shift still down", host_mods, phys_mods);
    phys_key(KC_RIGHT_SHIFT, false);

    printf("\nB: a spin, Left Shift tapped between two detents 80 ms apart, two more detents\n");
    reset_world();
    detent(VOLU);
    run_ms(30);
    phys_key(KC_LEFT_SHIFT, true);
    run_ms(25);
    phys_key(KC_LEFT_SHIFT, false);
    run_ms(25);
    detent(VOLU);
    run_ms(40);
    detent(VOLU);
    run_ms(500);
    printf("  consumer usages %d: %d with Shift+Alt, %d with Alt and no Shift\n", consumer_events, consumer_full_lsa,
           consumer_alt_only);
    if (consumer_alt_only) {
        printf("  FAIL %d volume usage(s) went out as Alt+Volume (Sound settings on macOS)\n", consumer_alt_only);
        fails++;
    } else
        printf("  ok   every usage carried Shift+Alt\n");

    printf("\nS: Alt/GUI swapped: the Left Alt key holds GUI; one detent, 0.5 s, the key released\n");
    reset_world();
    keymap_config.swap_lalt_lgui = true;
    phys_key(KC_LEFT_ALT, true);
    run_ms(30);
    detent(VOLU);
    run_ms(500);
    check("after the burst, the swapped key's GUI only", host_mods, phys_mods);
    phys_key(KC_LEFT_ALT, false);
    run_ms(50);
    check("the key released: nothing left held", host_mods, phys_mods);
    keymap_config.swap_lalt_lgui = false;

    printf("\nL: keyboard reports 4 ms late; Option held, Shift pressed 1 ms before the detent\n");
    reset_world();
    kb_latency_ms = 4;
    phys_key(KC_LEFT_ALT, true);
    run_ms(30);
    phys_key(KC_LEFT_SHIFT, true);
    run_ms(1);
    detent(VOLU);
    run_ms(30);
    printf("  consumer usages %d: %d with Shift+Alt, %d with Alt and no Shift\n", consumer_events, consumer_full_lsa,
           consumer_alt_only);
    if (consumer_events != 1 || consumer_full_lsa != 1) {
        printf("  FAIL the usage reached the host before the Shift did (Alt+Volume: Sound settings)\n");
        fails++;
    } else
        printf("  ok   the usage carried Shift+Alt\n");
    phys_key(KC_LEFT_SHIFT, false);
    phys_key(KC_LEFT_ALT, false);
    run_ms(500);
    kb_latency_ms = 0;
    run_ms(10);
    check("both released: nothing left held", host_mods, phys_mods);

    printf("\n%d failure(s)\n", fails);
    return fails ? 1 : 0;
}
