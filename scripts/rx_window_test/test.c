/* verify-043: the RX window's stale partial frame (ch582f_ajazz.c:1796).
 *
 * Drives the REAL ch582_task() (through bluetooth_task) with the environment
 * model from the audit's fuzz harness (sim.c: UART2 at 115200 8N1 into the
 * 128-byte input queue, ChibiOS ticks at 187.5 kHz, QMK's ms timer, a peer
 * that ACKs board frames when told to). Every scenario runs in its own
 * process (fork), so the driver's statics start at power-on each time.
 *
 * A main-loop pass runs every 3 ms (the loop's ~335 Hz).
 * conn_state: 0 IDLE, 1 LINKING, 2 PAIRING, 3 CONNECTED, 4 REJECTED. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "sim.h"
#include "ch582f_ajazz.h"
#include "bluetooth.h"

static void run_ms(uint32_t ms) {
    uint64_t end = S.T + MS_TICKS(ms);
    while (S.T < end) {
        sim_advance(MS_TICKS(3));
        bluetooth_task();
    }
}
static void push(const uint8_t *b, int n, uint32_t gap_us) {
    for (int i = 0; i < n; i++) sim_wire_push(b[i], i == 0 ? gap_us : 0);
}
static void frame(uint8_t t, uint8_t d) { uint8_t f[3] = {t, d, (uint8_t)(t + d)}; push(f, 3, 0); }
static void partial(uint8_t t, uint8_t d) { uint8_t f[2] = {t, d}; push(f, 2, 0); }  /* checksum byte lost */

static void boot_linked(bool peer_ack) {
    sim_reset();
    S.peer_ack    = peer_ack;
    S.peer_ack_us = 4000;
    bluetooth_init();
    ch582_set_profile(CH582_PROFILE_BT_1);
    run_ms(20);
    frame(0x5B, 0x32);           /* link established */
    run_ms(20);
}

static int expect(const char *name, int want_conn, int want_leds) {
    int conn = (int)ch582_get_conn_state();
    int leds = bluetooth_keyboard_leds();
    bool ok  = conn == want_conn && (want_leds < 0 || leds == want_leds);
    printf("%-58s conn=%d leds=%02X malformed=%u T=%.0f ms  -> %s (want conn=%d)\n", name, conn, leds,
           S.rx_malformed, S.T / 187.5, ok ? "as expected" : "WRONG", want_conn);
    return ok ? 0 : 1;
}

/* ---- scenarios ------------------------------------------------------------------ */

/* Control: the 5A frame whole, 425 ms quiet, then the link drops (5B 33). */
static int s_control(void) {
    boot_linked(false);
    frame(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("control: 5A 01 5B whole, 425 ms, 5B 33", 1, 0);
}
/* The finding's trigger: 5A 01's checksum (5B) lost, 425 ms quiet, then 5B 33. */
static int s_bug(void) {
    boot_linked(false);
    partial(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("bug: 5A 01 (cksum lost), 425 ms, 5B 33", 1, 0);
}
/* Time does not matter: 4.9 s of quiet (under one battery poll, no ACK from
 * the peer here, so nothing else crosses the line). */
static int s_bug_long(void) {
    boot_linked(false);
    partial(0x5A, 0x01);
    run_ms(4900);
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("bug: same, 4.9 s of quiet", 1, 0);
}
/* The module sends each LED change three times (docs/wireless.md:188). A lost
 * checksum in the first copy heals on the second ... */
static int s_triple_first_lost(void) {
    boot_linked(false);
    partial(0x5A, 0x01); frame(0x5A, 0x01); frame(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("3 copies, 1st cksum lost, 425 ms, 5B 33", 1, 0);
}
/* ... but one in the LAST copy leaves the window stale. */
static int s_triple_last_lost(void) {
    boot_linked(false);
    frame(0x5A, 0x01); frame(0x5A, 0x01); partial(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("3 copies, 3rd cksum lost, 425 ms, 5B 33", 1, 0);
}
/* With a peer that ACKs, the 5 s battery poll's ACK (61 0D 0A) crosses the
 * line and flushes the window harmlessly: the stale window lives until the
 * module's next byte, at most one poll period when idle. */
static int s_flushed_by_poll_ack(void) {
    boot_linked(true);
    run_ms(200);                 /* the boot's first poll and its ACK done */
    partial(0x5A, 0x01);
    run_ms(5600);                /* one poll + ACK at most 5 s later */
    frame(0x5B, 0x33);
    run_ms(30);
    return expect("ACKing peer: 5A 01 lost cksum, 5.6 s (poll ACK), 5B 33", 1, 0);
}
/* The module repeats 33/34 while it keeps attempting (findings-ch582-states.md
 * invariant 5): the second attempt's frame is parsed. */
static int s_second_attempt(void) {
    boot_linked(false);
    partial(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x33);
    run_ms(30);
    int before = (int)ch582_get_conn_state();
    run_ms(1000);
    frame(0x5B, 0x33);           /* the next connect attempt */
    run_ms(30);
    printf("  (after the first 5B 33: conn=%d)\n", before);
    return expect("bug then a 2nd 5B 33 one second later", 1, 0);
}
/* Single 5B 36 (attempt abandoned, persists; module never retracts it). */
static int s_bug_36(void) {
    boot_linked(false);
    partial(0x5A, 0x01);
    run_ms(425);
    frame(0x5B, 0x36);
    run_ms(30);
    return expect("bug: 5A 01 (cksum lost), 425 ms, 5B 36", 4, 0);
}
/* d=7 (Num+Caps+Scroll): 5A+7 = 0x61 eats the next ACK's first byte. With a
 * key report in flight, the ACK is lost: count the frames the peer received. */
static int s_eats_ack(void) {
    boot_linked(true);
    run_ms(200);
    frame(0x5A, 0x07);           /* host LEDs = 7, applied */
    run_ms(20);
    partial(0x5A, 0x07);         /* a repeat whose checksum is lost */
    run_ms(20);
    uint32_t f0 = S.peer_frames;
    report_keyboard_t r;
    memset(&r, 0, sizeof r);
    r.keys[0] = 0x04;
    bluetooth_send_keyboard(&r);
    run_ms(60);
    uint32_t sent = S.peer_frames - f0;
    printf("  (key report: the peer received %u frame(s) for one report; 1 = no retransmit)\n", sent);
    int fails = expect("d=7 stale window, then one key report", 3, 7);
    if (sent != 1) { printf("  -> WRONG: %u frames, the ACK was swallowed\n", sent); fails++; }
    return fails;
}
/* Control for s_eats_ack: the repeat whole. */
static int s_eats_ack_ctl(void) {
    boot_linked(true);
    run_ms(200);
    frame(0x5A, 0x07);
    run_ms(20);
    frame(0x5A, 0x07);
    run_ms(20);
    uint32_t f0 = S.peer_frames;
    report_keyboard_t r;
    memset(&r, 0, sizeof r);
    r.keys[0] = 0x04;
    bluetooth_send_keyboard(&r);
    run_ms(60);
    uint32_t sent = S.peer_frames - f0;
    printf("  (control key report: the peer received %u frame(s))\n", sent);
    int fails = expect("control: d=7 window whole, then one key report", 3, 7);
    if (sent != 1) { printf("  -> WRONG: %u frames\n", sent); fails++; }
    return fails;
}
/* Fix check: a frame that straddles two passes must still parse (the window
 * must NOT be cleared between a frame's bytes). 5A 01 lands, a pass drains it,
 * the checksum byte follows 2 ms later (much longer than the line's 87 us). */
static int s_straddle(void) {
    boot_linked(false);
    partial(0x5A, 0x02);
    sim_advance(MS_TICKS(1)); bluetooth_task();     /* drains 5A 02, queue empty */
    sim_wire_push(0x5C, 0);                         /* the checksum, now */
    sim_advance(MS_TICKS(1)); bluetooth_task();
    run_ms(10);
    return expect("straddle: 5A 02 | pass | 5C (frame split by a pass)", 3, 2);
}

typedef int (*scn_t)(void);
static const struct { const char *n; scn_t f; } scn[] = {
    {"control", s_control},           {"bug", s_bug},
    {"bug_long", s_bug_long},         {"triple_first_lost", s_triple_first_lost},
    {"triple_last_lost", s_triple_last_lost},
    {"flushed_by_poll_ack", s_flushed_by_poll_ack},
    {"second_attempt", s_second_attempt}, {"bug_36", s_bug_36},
    {"eats_ack_ctl", s_eats_ack_ctl}, {"eats_ack", s_eats_ack},         {"straddle", s_straddle},
};

int main(int argc, char **argv) {
    int bad = 0;
    for (size_t i = 0; i < sizeof scn / sizeof scn[0]; i++) {
        if (argc > 1 && strcmp(argv[1], scn[i].n) != 0) continue;
        fflush(stdout);
        pid_t p = fork();
        if (p == 0) { int r = scn[i].f(); fflush(stdout); _exit(r); }
        int st = 0;
        waitpid(p, &st, 0);
        if (!WIFEXITED(st)) { printf("%s: CRASHED (signal %d)\n", scn[i].n, WTERMSIG(st)); bad++; }
        else bad += WEXITSTATUS(st);
    }
    printf("== %d scenario(s) not as a correct driver would leave them\n", bad);
    return 0;
}
