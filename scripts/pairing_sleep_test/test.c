/* An abandoned pairing must not hold off deep sleep (plans/AUDIT-2026-10-31.md,
 * F-003; first written as the audit's verify-000).
 *
 * The real ch582f_ajazz.c (radio driver), bt_ui.c (the slot key's hold-to-
 * pair) and sleep.c (sleep_task / blockers) run together, by path, unedited.
 * Each simulated ms is one main-loop pass: module_tick(), ch582_task(),
 * bt_pair_hold_task() every 100 ms (its 10 Hz tick), sleep_task(). The module
 * model is world_radio.c's.
 *
 *   ./test A   hold Fn+W 2.3 s, pair nothing, walk away
 *   ./test B   control: a plain tap on Fn+W, walk away
 *   ./test C   A, then a tap on Fn+W at 30 min
 *   ./test D   A, with a module that reconnects the old host after advertising
 *   ./test E   A, with the 5B 31 lost on the wire: PA_PAIR gives up
 *
 * Each must reach the ladder's sleep 20 min (Balanced) after the last key;
 * before the fix A and E never slept. In A and E the link state stays
 * PAIRING after the pairing flag lapses, so a tap still takes the
 * cancel-pairing bounce. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hal.h"
#include "quantum.h"
#include "ak820pro.h"
#include "bt_ui.h"
#include "sleep.h"
#include "bluetooth/ch582f_ajazz.h"

extern uint32_t now_ms, sleep_eligible_passes, first_eligible_ms, last_input_ms;
extern int key_down;
extern bool mod_reconnect_after_adv, mod_drop_next_5b31;
extern uint32_t mod_frames_5b[256];
void module_tick(void);
void module_verbose(int v);
void bluetooth_init(void);

#define DSB_PAIRING 0x0400u

static const char *st(void) {
    static const char *n[] = {"IDLE", "LINKING", "PAIRING", "CONNECTED", "REJECTED"};
    return n[ch582_get_conn_state()];
}
static uint16_t wanted_blocked(void) {
    uint8_t pg[SLEEP_PAGE1_SIZE];
    sleep_page1_fill(pg);   /* HC_POWER page 1; ds_wanted_blocked at [26..27] */
    return (uint16_t)(pg[26] | (pg[27] << 8));
}

/* blocker masks seen while a sleep was wanted, and for how long */
static uint32_t ms_wanted = 0, ms_wanted_pairing = 0, ms_wanted_only_pairing = 0;

static void pass(void) {
    module_tick();
    ch582_task();
    if (now_ms % 100 == 0) bt_pair_hold_task();
    uint32_t before = sleep_eligible_passes;
    sleep_task();
    if (last_input_activity_elapsed() >= 1200000u) {
        ms_wanted++;
        uint16_t b = wanted_blocked();
        if (b & DSB_PAIRING) ms_wanted_pairing++;
        if (b == DSB_PAIRING) ms_wanted_only_pairing++;
        (void)before;
    }
    now_ms++;
}
static void run_until(uint32_t t) { while (now_ms < t) pass(); }

static void key(uint16_t kc, bool down) {
    keyrecord_t r;
    memset(&r, 0, sizeof r);
    r.event.pressed = down;
    key_down        = down;
    last_input_ms   = now_ms;
    bt_ui_slot_key(kc, &r);
}

static void report(const char *when) {
    printf("  [%8.3f s] %-44s conn=%-9s is_pairing=%d  wanted_blocked=0x%04X  sleep-eligible passes=%u\n",
           now_ms / 1000.0, when, st(), ch582_is_pairing(), wanted_blocked(), sleep_eligible_passes);
}

int main(int argc, char **argv) {
    char sc = argc > 1 ? argv[1][0] : 'A';
    uint32_t end_ms = (argc > 2 ? (uint32_t)atoi(argv[2]) : 120u) * 60000u;   /* minutes */
    if (sc == 'D') mod_reconnect_after_adv = true;
    if (sc == 'E') mod_drop_next_5b31 = true;
    module_verbose(1);
    printf("scenario %c, %u simulated minutes\n", sc, end_ms / 60000u);

    bluetooth_init();
    run_until(10);
    bt_ui_mode_slider(1, true);    /* slider on BT: slot 1 selected, its host reconnects */
    run_until(2000);
    report("BT up on slot 1");

    run_until(5000);
    key(BT2, true);                /* Fn+W pressed: select slot 2 */
    if (sc == 'B') {
        run_until(5100);
        key(BT2, false);           /* a tap */
    } else {
        run_until(7300);           /* held past BT_PAIR_HOLD_MS (2 s): A6 51 */
        key(BT2, false);
    }
    run_until(8000);
    report(sc == 'B' ? "after the tap" : "after the hold (pairing)");

    run_until(190000);
    report("after the advertising window (3 min)");

    if (sc == 'C') {
        run_until(30u * 60000u);
        report("30 min: before the tap on Fn+W");
        key(BT2, true);
        run_until(30u * 60000u + 100);
        key(BT2, false);
        run_until(30u * 60000u + 2000);
        report("after the tap (bounce, then select)");
    }

    module_verbose(0);
    run_until(end_ms);
    report("end");

    printf("  sleep wanted (idle >= 20 min, Balanced) for %u s; DSB_PAIRING set for %u s of it, "
           "DSB_PAIRING the only blocker for %u s\n",
           ms_wanted / 1000u, ms_wanted_pairing / 1000u, ms_wanted_only_pairing / 1000u);
    if (sleep_eligible_passes)
        printf("  first pass where sleep.c would enter deep sleep: %.3f s\n", first_eligible_ms / 1000.0);
    else
        printf("  sleep.c never reached the sleep (rtc_sleep_prepare never called)\n");
    printf("  5B frames the driver received: 31 x%u, 32 x%u, 33 x%u, 23 x%u\n", mod_frames_5b[0x31],
           mod_frames_5b[0x32], mod_frames_5b[0x33], mod_frames_5b[0x23]);

    int fails = 0;
    /* the last key: the tap or the hold's release at 5.1 / 7.3 s, or C's tap at 30 min */
    uint32_t last_key_ms = sc == 'B' ? 5100u : 7300u;
    if (!sleep_eligible_passes) { printf("FAIL: never reached the sleep\n"); fails++; }
    else if (first_eligible_ms > last_key_ms + 1200000u + 1000u) {
        printf("FAIL: slept at %.3f s, later than 20 min after the last key\n", first_eligible_ms / 1000.0);
        fails++;
    }
    if (ms_wanted_only_pairing) { printf("FAIL: DSB_PAIRING alone held off a wanted sleep for %u ms\n", ms_wanted_only_pairing); fails++; }
    if ((sc == 'A' || sc == 'E') && ch582_get_conn_state() != CH582_CONN_PAIRING) {
        printf("FAIL: the link state left PAIRING (%s): a tap would no longer bounce\n", st());
        fails++;
    }
    printf("RESULT %c: %s\n", sc, fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}
