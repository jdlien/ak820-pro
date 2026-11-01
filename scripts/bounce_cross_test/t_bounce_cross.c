/* verify-001: the cancel-pairing bounce for a CROSS-slot tap.
 *
 * Compiles, by path and unedited, the real bt_ui.c (the slot keys) and the
 * real bluetooth/ch582f_ajazz.c (the CH582F driver), daily-build config (no
 * DEV/WDT/CONSOLE hooks). The CH582F itself is a small MODEL built only from
 * the behaviour docs/wireless.md records as measured:
 *   - every frame is ACKed (61 0D 0A) ~4 ms later;
 *   - A6 <slot> naming the slot that is ADVERTISING is a no-op (silent);
 *   - A6 <slot> naming any other slot is honoured at once: the link (or the
 *     advertising) drops, the module attempts that slot (5B 33), and a bonded
 *     host in range links after its latency (5B 32);
 *   - A6 51 puts the selected slot into advertising (5B 31) unless an attempt
 *     is in flight (dropped then); an unbonded slot's attempt ends 5B 36;
 *   - A1 keyboard frames reach whichever host is linked, else nowhere.
 *
 * For each (advertising slot X, tapped slot Y) it holds Fn+<X> 2 s to pair,
 * waits for 5B 31, taps Fn+<Y>, types one key 400 ms later, and records the
 * select frames, where the module went, where the key landed, and what the
 * board's band would read 600 ms after the tap. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "stubs/hal.h"
#include "stubs/quantum.h"
#include "ch582f_ajazz.h"
#include "bt_ui.h"
#include "ak820pro.h"
#include "stubs/connection.h"
#undef printf

/* ---------------- platform stubs ---------------- */
SerialDriver SD2;
bool loop_acct_on = false;
static uint32_t now_ms = 0;
static uint8_t rxq[8192];
static size_t rx_h = 0, rx_t = 0;
static eventflags_t pending_flags = 0;

void sdStart(SerialDriver *sdp, const SerialConfig *cfg) { (void)sdp; (void)cfg; }
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t) {
    (void)sdp; (void)t; size_t k = 0;
    while (k < n && rx_h != rx_t) { b[k++] = rxq[rx_h]; rx_h = (rx_h + 1) % sizeof rxq; }
    return k;
}
void chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f) { (void)es; (void)el; (void)m; (void)f; }
eventflags_t chEvtGetAndClearFlags(event_listener_t *el) { (void)el; eventflags_t f = pending_flags; pending_flags = 0; return f; }
uint16_t timer_read(void) { return (uint16_t)now_ms; }
uint32_t timer_read32(void) { return now_ms; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)((uint64_t)now_ms * CH_CFG_ST_FREQUENCY / 1000u); }
uint16_t timer_elapsed(uint16_t t) { return (uint16_t)((uint16_t)now_ms - t); }
uint32_t timer_elapsed32(uint32_t t) { return now_ms - t; }
void battery_5c_report(uint8_t d) { (void)d; }
void health_note_rx_malformed(void) {}
void clear_keyboard(void) {}
void connection_set_host_noeeprom(connection_host_t host) { (void)host; }
static uint8_t ee_bt_profile = CH582_PROFILE_BT_1;
uint8_t kb_eeconfig_get_bt_profile(void) { return ee_bt_profile; }
void kb_eeconfig_set_bt_profile(uint8_t p) { ee_bt_profile = p; }
void display_set_pair_hint(int16_t pct) { (void)pct; }
void display_draw_usb_logo(void) {}
void display_draw_bluetooth_logo(void) {}
void display_draw_2_4_g_logo(void) {}
void bluetooth_init(void);

/* ---------------- the CH582F model ---------------- */
#define MAXEV 512
typedef struct { uint32_t t; uint8_t b[3]; uint8_t n; int link_gen; int link_slot; } ev_t;
static ev_t evq[MAXEV];
static int nev = 0;
enum { M_IDLE, M_ATTEMPT, M_LINKED, M_ADVERT };
static int mod_mode = M_IDLE, mod_slot = 0, linked_host = 0, link_gen = 0;
static uint32_t host_latency[4] = {0, 300, 300, 300};   /* every slot bonded, host in range */
static int keys_to_host[4];      /* key-down A1 frames delivered, per slot's host; [0] = nowhere */
static int bounce_visits[4];     /* slots the module was sent to (attempted) after the tap */
static bool after_tap = false;

/* select frames sent by the board, after the tap */
static struct { uint32_t t; uint8_t slot; } sel_log[32];
static int nsel = 0;
static uint32_t tap_time = 0;

static void sched(uint32_t dt, const uint8_t *b, uint8_t n, int gen, int slot) {
    if (nev >= MAXEV) { fprintf(stderr, "event queue full\n"); exit(2); }
    ev_t *e = &evq[nev++];
    e->t = now_ms + dt; memcpy(e->b, b, n); e->n = n; e->link_gen = gen; e->link_slot = slot;
}
static void sched3(uint32_t dt, uint8_t t, uint8_t d) { uint8_t f[3] = {t, d, (uint8_t)(t + d)}; sched(dt, f, 3, 0, 0); }

static void module_select(int s) {
    if (mod_mode == M_ADVERT && s == mod_slot) return;   /* the measured no-op */
    link_gen++;                                          /* cancels a scheduled link-up */
    mod_mode = M_ATTEMPT; mod_slot = s; linked_host = 0;
    if (after_tap) bounce_visits[s]++;
    sched3(20, 0x5B, 0x33);
    if (host_latency[s]) {
        uint8_t f[3] = {0x5B, 0x32, (uint8_t)(0x5B + 0x32)};
        sched(host_latency[s], f, 3, link_gen, s);
    } else {
        uint8_t f[3] = {0x5B, 0x36, (uint8_t)(0x5B + 0x36)};
        sched(300, f, 3, link_gen, -s);
    }
}

size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n) {
    (void)sdp;
    static const uint8_t ackf[3] = {0x61, 0x0D, 0x0A};
    sched(4, ackf, 3, 0, 0);
    if (n == 3 && b[0] == 0xA6) {
        uint8_t p = b[1];
        if (p >= 0x31 && p <= 0x33) {
            if (after_tap && nsel < 32) { sel_log[nsel].t = now_ms - tap_time; sel_log[nsel].slot = p - 0x30; nsel++; }
            module_select(p - 0x30);
        } else if (p == 0x51) {
            if (mod_mode != M_ATTEMPT) { link_gen++; mod_mode = M_ADVERT; linked_host = 0; sched3(30, 0x5B, 0x31); }
        } else if (p == 0x53) {
            sched3(10, 0x5C, 80);
        }
    } else if (n == 10 && b[0] == 0xA1) {
        bool down = false; for (int i = 3; i < 9; i++) if (b[i]) down = true;
        if (down) keys_to_host[mod_mode == M_LINKED ? linked_host : 0]++;
    }
    return n;
}

static void deliver_due(void) {
    for (int i = 0; i < nev;) {
        if (evq[i].t <= now_ms) {
            ev_t e = evq[i];
            evq[i] = evq[--nev];
            if (e.link_slot != 0) {
                if (e.link_gen != link_gen) continue;              /* superseded */
                if (e.link_slot > 0) { mod_mode = M_LINKED; linked_host = e.link_slot; }
                else mod_mode = M_IDLE;
            }
            for (int k = 0; k < e.n; k++) { rxq[rx_t] = e.b[k]; rx_t = (rx_t + 1) % sizeof rxq; }
        } else i++;
    }
}

static void run(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i++) {
        deliver_due();
        ch582_task();
        if (now_ms % 100 == 0) bt_pair_hold_task();   /* the 10 Hz housekeeping tick */
        now_ms++;
    }
}

static const char *stname(ch582_conn_state_t s) {
    static const char *n[] = {"IDLE", "LINKING", "PAIRING", "CONNECTED", "REJECTED"};
    return n[s];
}
static uint16_t slot_key(int s) { return s == 1 ? BT1 : s == 2 ? BT2 : BT3; }
static void press(int s, bool down) { keyrecord_t r = {.event = {.pressed = down}}; bt_ui_slot_key(slot_key(s), &r); }
static void type_key(uint8_t kc) {
    report_keyboard_t r; memset(&r, 0, sizeof r); r.keys[0] = kc; ch582_send_keyboard_report(&r);
    run(30);
    memset(&r, 0, sizeof r); ch582_send_keyboard_report(&r);
}

/* One case, in its own process so every static starts fresh. */
static int expired = 0;   /* scenario 2: the advertising window ended (5B 23) before the tap */
static int one_case(int X, int Y) {
    bluetooth_init();
    bt_ui_mode_slider(1, true);          /* slider on BT */
    bt_ui_resume_saved_profile();
    run(1500);

    /* hold Fn+<X> past 2 s: select X, then A6 51 */
    press(X, true); run(2300); press(X, false); run(700);
    if (ch582_get_conn_state() != CH582_CONN_PAIRING || mod_mode != M_ADVERT) {
        printf("X=%d Y=%d: setup failed (state %s, model mode %d)\n", X, Y, stname(ch582_get_conn_state()), mod_mode);
        return 3;
    }

    if (expired) {
        /* Nobody paired: minutes later the module stops advertising, says 5B 23
         * (which the driver ignores) and idles. The user later switches slots. */
        run(60000);
        link_gen++; mod_mode = M_IDLE; sched3(0, 0x5B, 0x23);
        run(120000);
        if (ch582_get_conn_state() != CH582_CONN_PAIRING) { printf("adv %d, tap %d: state left PAIRING (%s)\n", X, Y, stname(ch582_get_conn_state())); }
    }
    /* tap Fn+<Y> */
    after_tap = true; tap_time = now_ms;
    press(Y, true); run(100); press(Y, false); run(300);   /* +400 ms */
    type_key(0x04);                                        /* 'a' at +400 */
    run(170);                                              /* +600 */
    ch582_conn_state_t st600 = ch582_get_conn_state();
    uint8_t slot600 = ch582_get_slot(), tgt600 = ch582_get_target_slot();
    int mod600 = mod_mode == M_LINKED ? linked_host : 0;
    run(1400);                                             /* +2000 */

    printf("%sadv %d, tap %d: selects", expired ? "[expired 3 min ago] " : "", X, Y);
    for (int i = 0; i < nsel; i++) printf(" A6 3%u@+%ums", sel_log[i].slot, (unsigned)sel_log[i].t);
    int first = nsel ? sel_log[0].slot : 0;
    const char *kind;
    if (first == Y) kind = "direct";
    else if (X == Y) kind = "bounce (same slot: documented)";
    else if (first == X) kind = expired ? "BOUNCE via the formerly advertising slot (idle now, so not a no-op)"
                                        : "BOUNCE via the advertising slot itself (no-op, +700 ms)";
    else kind = "BOUNCE via an unrelated THIRD slot";
    printf("  -> %s\n", kind);
    printf("    @+600: band %s, connected_slot %u, target %u; module linked to slot %d's host\n",
           stname(st600), slot600, tgt600, mod600);
    printf("    key typed @+400 went to: %s\n",
           keys_to_host[0] ? "nowhere (module not linked)" :
           keys_to_host[Y] ? "the TARGET slot's host" : "a DIFFERENT host than the target");
    for (int s = 1; s <= 3; s++)
        if (keys_to_host[s]) printf("      (slot %d's host received %d key press)\n", s, keys_to_host[s]);
    printf("    final: band %s, slot %u; module on slot %d (%s)\n", stname(ch582_get_conn_state()),
           ch582_get_slot(), mod_slot, mod_mode == M_LINKED ? "linked" : "not linked");
    /* exit code: 0 = direct or the documented same-slot bounce; 10 = gratuitous no-op bounce; 20 = third slot */
    if (expired && X == Y && first != Y) return 30;   /* not advertising: even a same-slot bounce is needless */
    if (first == Y || X == Y) return 0;
    return first == X ? 10 : 20;
}

int main(int argc, char **argv) {
    int third = 0, noop = 0, ok = 0, needless_same = 0;
    expired = argc > 1 && strcmp(argv[1], "--expired") == 0;
    for (int X = 1; X <= 3; X++)
        for (int Y = 1; Y <= 3; Y++) {
            fflush(stdout);
            pid_t pid = fork();
            if (pid == 0) { int rc_ = one_case(X, Y); fflush(stdout); _exit(rc_); }
            int status = 0; waitpid(pid, &status, 0);
            int rc = WIFEXITED(status) ? WEXITSTATUS(status) : 99;
            if (rc == 0) ok++; else if (rc == 10) noop++; else if (rc == 20) third++; else if (rc == 30) needless_same++;
            else { printf("case %d/%d: abnormal exit %d\n", X, Y, rc); return 1; }
        }
    printf("\nSUMMARY: %d as documented (direct or same-slot bounce), %d cross-slot bounces through the advertising slot (+700 ms), %d cross-slot bounces through an unrelated third slot\n",
           ok, noop, third);
    if (expired) printf("         %d same-slot bounces after the advertising had already ended\n", needless_same);
    return third ? 1 : 0;   /* nonzero while the bug is present */
}
