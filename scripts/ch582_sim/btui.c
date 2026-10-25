/* bt_ui.c's menu calls on the real driver (P3, plans/CONFIG-MENU-P1-DESIGN.md;
 * codex on its design: the sequences need the driver, not a fake of it).
 *
 * bt_ui.c and ch582f_ajazz.c are compiled VERBATIM, on harness.c's world (a
 * millisecond clock, recorded UART writes, injected reads) and stubs_btui/
 * (the settings block, the host switch, the display). The module ACKs every
 * frame; its 5B state frames are the case's. The main loop runs at 1 kHz and
 * bt_ui's tick at 10 Hz, as on the board. One case per process. Build and run
 * with run.sh. */
#define HARNESS_NO_MAIN
#include "harness.c"
#include "bt_ui.h"
#include "kb_eeconfig.h"
#include "connection.h"
#include "graphics/display.h"
#include "ak820pro.h"   /* the slot keys' codes */

/* The settings block's slot, the host switch, the logo. */
static uint8_t saved = 0x31;
static int     saves, hosts, bt_logos, clears;
uint8_t        kb_eeconfig_get_bt_profile(void) { return saved; }
void           kb_eeconfig_set_bt_profile(uint8_t p) { saved = p; saves++; }
void           connection_set_host_noeeprom(connection_host_t h) { (void)h; hosts++; }
void           display_draw_bluetooth_logo(void) { bt_logos++; }
void           display_draw_2_4_g_logo(void) {}
void           display_draw_usb_logo(void) {}
void           display_set_pair_hint(int16_t pct) { (void)pct; }
void           clear_keyboard(void) { clears++; }

/* The loop: the driver's task each ms, every written frame ACKed (but the
 * driver's own ACK tokens), bt_ui's tick every 100 ms. */
static int acked;
static void run(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i++) {
        ch582_task();
        for (; acked < wr_n; acked++)
            if (wr[acked][0] != 0x61) rx_ack();
        if (now_ms % 100 == 0) bt_pair_hold_task();
        now_ms++;
    }
}
static void frame(uint8_t type, uint8_t d) {
    uint8_t f[3] = {type, d, (uint8_t)(type + d)};
    rx_feed(f, 3);
    run(20);
}
/* A6 <param> frames written since `from`; and the first one's index (-1). */
static int a6(uint8_t param, int from) {
    int n = 0;
    for (int i = from; i < wr_n; i++)
        if (wr_len[i] == 3 && wr[i][0] == 0xA6 && wr[i][1] == param) n++;
    return n;
}
static int a6_at(uint8_t param, int from) {
    for (int i = from; i < wr_n; i++)
        if (wr_len[i] == 3 && wr[i][0] == 0xA6 && wr[i][1] == param) return i;
    return -1;
}
#define PAIR 0x51

/* Boot with the slider on BT, the saved slot `p`, and the link up. */
static void boot_linked(uint8_t p) {
    saved = p;
    bt_ui_mode_slider(1, true);
    bt_ui_resume_saved_profile();
    run(50);
    frame(0x5B, 0x33);
    frame(0x5B, 0x32);
    CHECK(ch582_get_conn_state() == CH582_CONN_CONNECTED && ch582_select_state() == CH582_SEL_ACKED, "booted linked");
}
/* Advertising on the current slot, confirmed (the key's hold). */
static void advertising(void) {
    ch582_enter_pairing();
    run(50);
    frame(0x5B, 0x31);
    CHECK(ch582_get_conn_state() == CH582_CONN_PAIRING && ch582_pair_confirmed() && !ch582_pair_retrying(),
          "advertising, confirmed");
}

/* The menu's select is the key's tap: saved, selected, BT, the logo; no pair. */
static void tap_select(void) {
    boot_linked(0x31);
    int from = wr_n, s0 = saves, h0 = hosts, l0 = bt_logos;
    bt_ui_select_slot(1);
    run(30);
    CHECK(a6(0x32, from) == 1 && saved == 0x32 && saves == s0 + 1 && hosts == h0 + 1 && bt_logos == l0 + 1,
          "the tap's select: %d sent, saved %02X", a6(0x32, from), saved);
    CHECK(ch582_select_state() == CH582_SEL_PENDING && !bt_ui_pair_waiting(), "pending, no pair armed");
    frame(0x5B, 0x33);
    frame(0x5B, 0x32);
    run(3000);
    CHECK(a6(PAIR, from) == 0 && ch582_select_state() == CH582_SEL_ACKED, "never a pair");
}

/* The current slot, linked: no select, the pair on the next tick. */
static void pair_current_linked(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(0);
    CHECK(bt_ui_pair_waiting() && a6(0x31, from) == 0, "waiting, nothing selected");
    run(110);
    CHECK(a6(PAIR, from) == 1 && !bt_ui_pair_waiting() && ch582_pair_retrying() && !ch582_pair_confirmed(),
          "the pair sent within a tick: %d", a6(PAIR, from));
    frame(0x5B, 0x31);
    CHECK(ch582_pair_confirmed() && !ch582_pair_retrying() && ch582_get_conn_state() == CH582_CONN_PAIRING,
          "confirmed advertising");
}

/* Another slot: its select, then the pair once the attempt ends (rejected),
 * never mid-attempt. */
static void pair_other_rejected(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(2);
    run(30);
    CHECK(a6(0x33, from) == 1 && saved == 0x33 && ch582_select_state() == CH582_SEL_PENDING, "the select first");
    run(1000);
    frame(0x5B, 0x33);
    run(3000);
    CHECK(a6(PAIR, from) == 0 && bt_ui_pair_waiting(), "not mid-attempt");
    frame(0x5B, 0x36);
    run(110);
    CHECK(a6(PAIR, from) == 1 && a6_at(PAIR, from) > a6_at(0x33, from) && !bt_ui_pair_waiting(), "sent after 5B 36");
}

/* Mid-attempt the whole time: sent at 6 s, the driver's retry from there. */
static void pair_other_cap(void) {
    boot_linked(0x31);
    int from = wr_n;
    uint32_t t0 = now_ms;
    bt_ui_pair_slot(2);
    run(200);
    frame(0x5B, 0x33);
    run(5900 - (now_ms - t0));
    CHECK(a6(PAIR, from) == 0, "not before 6 s");
    run(300);
    CHECK(a6(PAIR, from) >= 1 && !bt_ui_pair_waiting(), "sent at 6 s");
}

/* The slot's old host reconnects first: the pair goes to the live link (the
 * hold's fast case). */
static void pair_other_oldhost(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(1);
    run(200);
    frame(0x5B, 0x33);
    frame(0x5B, 0x32);
    run(110);
    CHECK(a6(PAIR, from) == 1, "the pair on the old host's link: %d", a6(PAIR, from));
}

/* Codex's must-fix 1: from advertising, another slot's select is a bounce;
 * the bounce slot's 5B 32 must not fire the pair, which would replace the
 * bounce and pair the bounce slot. */
static void pair_bounce(void) {
    boot_linked(0x31);
    advertising();
    int from = wr_n;
    bt_ui_pair_slot(2);   /* BT 3: the bounce goes through BT 1 */
    run(100);
    CHECK(a6(0x31, from) == 1 && a6(0x33, from) == 0, "the bounce's first half");
    frame(0x5B, 0x32);    /* the bounce slot links up */
    CHECK(ch582_get_conn_state() == CH582_CONN_CONNECTED && ch582_select_state() == CH582_SEL_PENDING,
          "connected, the select still pending");
    run(300);
    CHECK(a6(PAIR, from) == 0, "no pair in the bounce");
    run(500);
    CHECK(a6(0x33, from) == 1, "the real select at 700 ms");
    frame(0x5B, 0x33);
    frame(0x5B, 0x36);
    run(110);
    CHECK(a6(PAIR, from) == 1 && a6_at(PAIR, from) > a6_at(0x33, from), "the pair after the target's select");
}

/* Codex's must-fix 3: a select never answered (its 8 tries run out) gets no
 * pair; the next pair on that slot selects it again. */
static void pair_lost_select(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(2);
    run(15000);
    CHECK(a6(0x33, from) == 8 && ch582_select_state() == CH582_SEL_LOST, "eight tries, lost: %d", a6(0x33, from));
    CHECK(a6(PAIR, from) == 0 && !bt_ui_pair_waiting(), "no pair, disarmed");
    CHECK(ch582_get_conn_state() == CH582_CONN_LINKING, "the state stays the optimistic linking");
    int from2 = wr_n;
    bt_ui_pair_slot(2);   /* the current slot now, but lost: selected again */
    run(30);
    CHECK(a6(0x33, from2) == 1 && bt_ui_pair_waiting(), "selected again, waiting");
}

/* Codex's must-fix 2: a menu select, a slot key, Fn+P or the slider each
 * supersede a pending pair. */
static void pair_superseded(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(2);
    run(200);
    frame(0x5B, 0x33);
    bt_ui_select_slot(0);
    CHECK(!bt_ui_pair_waiting(), "the menu's select");
    frame(0x5B, 0x33);
    frame(0x5B, 0x36);
    run(7000);
    CHECK(a6(PAIR, from) == 0, "never sent: %d", a6(PAIR, from));
    keyrecord_t down = {{true}}, up = {{false}};
    bt_ui_pair_slot(1);
    CHECK(bt_ui_pair_waiting(), "armed");
    bt_ui_slot_key(BT3, &down);
    bt_ui_slot_key(BT3, &up);
    CHECK(!bt_ui_pair_waiting(), "a slot key");
    bt_ui_pair_slot(1);
    bt_ui_pair_key(&down);
    bt_ui_pair_key(&up);
    CHECK(!bt_ui_pair_waiting(), "Fn+P");
    bt_ui_pair_slot(1);
    bt_ui_mode_slider(1, false);   /* to 2.4G: both pins, as the slider moves them */
    CHECK(!bt_ui_pair_waiting(), "the slider");
    bt_ui_mode_slider(2, true);
    int from2 = wr_n;
    bt_ui_select_slot(0);
    bt_ui_pair_slot(0);
    bt_ui_pair_stop();
    run(500);
    CHECK(a6(0x31, from2) == 0 && a6(PAIR, from2) == 0 && !bt_ui_pair_waiting(), "off BT: nothing");
}

/* Codex's must-fix 4: the 5B 31 lost, the retry gives up: still the
 * optimistic PAIRING, and the stop's select cancels it (the bounce). */
static void pair_lost_confirm(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(0);
    run(6000);
    CHECK(a6(PAIR, from) == 12 && !ch582_pair_retrying() && !ch582_pair_confirmed() &&
              ch582_get_conn_state() == CH582_CONN_PAIRING,
          "twelve tries, unconfirmed, optimistic: %d", a6(PAIR, from));
    int from2 = wr_n;
    bt_ui_pair_stop();
    run(1000);
    CHECK(a6(0x32, from2) == 1 && a6(0x31, from2) == 1 && a6_at(0x31, from2) > a6_at(0x32, from2),
          "the bounce, then the slot");
}

/* A missed 5B 32, recovered by the 5A promotion: acted on, so the pair goes. */
static void pair_promotion(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(2);
    run(200);
    frame(0x5A, 0x00);   /* too soon: not promoted */
    CHECK(ch582_get_conn_state() == CH582_CONN_LINKING && a6(PAIR, from) == 0, "not yet");
    run(3000);
    frame(0x5A, 0x00);
    run(110);
    CHECK(ch582_get_conn_state() != CH582_CONN_LINKING && a6(PAIR, from) == 1, "promoted, the pair sent");
}

/* The stop: only the wait while linking; the cancel while advertising or
 * resending; nothing on a quiet link. */
static void stop_cases(void) {
    boot_linked(0x31);
    int from = wr_n;
    bt_ui_pair_slot(2);
    run(200);
    frame(0x5B, 0x33);
    int from2 = wr_n;
    bt_ui_pair_stop();
    run(1000);
    CHECK(!bt_ui_pair_waiting() && wr_n == from2 + a6(0x53, from2), "waiting: only disarmed (%d frames)", wr_n - from2);
    frame(0x5B, 0x32);
    advertising();
    from2 = wr_n;
    bt_ui_pair_stop();
    run(1000);
    CHECK(a6(0x31, from2) == 1 && a6(0x33, from2) == 1, "advertising: the bounce and the slot");
    frame(0x5B, 0x33);
    frame(0x5B, 0x32);
    bt_ui_pair_slot(2);   /* current, linked: the pair next tick */
    run(110);
    CHECK(ch582_pair_retrying(), "resending");
    from2 = wr_n;
    bt_ui_pair_stop();
    run(1000);
    CHECK(a6(0x33, from2) >= 1 && !ch582_pair_retrying(), "resending: the select");
    frame(0x5B, 0x33);
    frame(0x5B, 0x32);
    from2 = wr_n;
    bt_ui_pair_stop();
    run(1000);
    CHECK(wr_n == from2 + a6(0x53, from2), "linked, nothing pending: nothing sent");
    (void)from;
}

/* Already advertising: a pair sends nothing; and a slot that starts
 * advertising by itself before the pair fires is left as it is. */
static void already_advertising(void) {
    boot_linked(0x31);
    advertising();
    int from = wr_n;
    bt_ui_pair_slot(0);
    run(500);
    CHECK(!bt_ui_pair_waiting() && a6(PAIR, from) == 0 && a6(0x31, from) == 0, "nothing");
    frame(0x5B, 0x32);
    from = wr_n;
    bt_ui_pair_slot(1);
    run(30);
    frame(0x5B, 0x31);
    run(200);
    CHECK(!bt_ui_pair_waiting() && a6(PAIR, from) == 0, "advertising by itself: no pair");
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: btui CASE\n"); return 2; }
    static const struct { const char *name; void (*fn)(void); } cases[] = {
        {"tap_select", tap_select}, {"pair_current_linked", pair_current_linked},
        {"pair_other_rejected", pair_other_rejected}, {"pair_other_cap", pair_other_cap},
        {"pair_other_oldhost", pair_other_oldhost}, {"pair_bounce", pair_bounce},
        {"pair_lost_select", pair_lost_select}, {"pair_superseded", pair_superseded},
        {"pair_lost_confirm", pair_lost_confirm}, {"pair_promotion", pair_promotion},
        {"stop_cases", stop_cases}, {"already_advertising", already_advertising},
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++)
        if (!strcmp(argv[1], cases[i].name)) {
            cases[i].fn();
            printf("%s btui %s\n", failures ? "FAIL" : "ok  ", argv[1]);
            return failures ? 1 : 0;
        }
    fprintf(stderr, "unknown case %s\n", argv[1]);
    return 2;
}
