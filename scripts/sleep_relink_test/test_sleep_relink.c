/* A link that comes up while the MCU deep-sleeps (plans/AUDIT-2026-10-31.md,
 * F-023; first written as the audit's verify-003, which showed the stuck
 * states). Since the fix: a link attempt under 60 s old holds off the sleep
 * (ch582_linking_recent(), sleep.c's DSB_LINKING); the 5A promotion fires
 * from REJECTED too; and after a sleep the link state reads stale
 * (ch582_link_state_stale()) until the module names one, so the band names no
 * remedy. A (LINKING, no lock change after) stays LINKING: nothing tells the
 * board, and LINKING's band names no remedy; D (REJECTED) now recovers at the
 * first Caps change. The original description follows.
 *
 * verify-003: a link that comes up while the MCU deep-sleeps.
 *
 * The real bluetooth/ch582f_ajazz.c is compiled verbatim (fw_unit.c #includes
 * it by absolute path); sim.c is the UART/peer/clock model from the audit's
 * fuzz-ch582-rx harness (S.rx_off == the receiver off: a byte arriving then is
 * lost, as sleep.c:460-461 `SN_UART2->CTRL = uart_ctrl & ~UART_CTRL_RXEN;`).
 *
 * The deep sleep is modelled the way sleep.c sequences it:
 *   entry : RXEN cleared (S.rx_off = true); no main-loop passes run;
 *           QMK's ms timer stands still (the system-time counter is stopped:
 *           sleep.c's `SN32_ST_TIM->config.TMRCTRL &= ~mskCT16_CEN_EN`), so
 *           S.ms_off is pulled back by the slept time;
 *   exit  : RXEN back, the receiver drained and iqResetI(&SD2.iqueue),
 *           ch582_rx_resync() (sleep.c:614), ch582_sleep_wake() from
 *           recovery_begin() (sleep.c:676), then ch582_battery_poll_release()
 *           once the waking key's report has gone (sleep.c:729).
 *
 * What the module does is modelled from docs/wireless.md: `5B 32` is sent once
 * at link-up; the host's LED report is forwarded as `5A <bits> <sum>`, every
 * change three times 0-5 ms apart, and a repeat of the same value is NOT
 * forwarded; `5B 23` is periodic and ambiguous; `5C` answers the A6 53 poll.
 * Whether the module really re-links on its own while the MCU sleeps is the
 * hardware question this test cannot answer: it is the scenario's premise. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "fw_access.h"
#include "ch582f_ajazz.h"
#include "bluetooth.h"

extern int sim_verbose;
uint32_t timer_read32(void);

/* The driver's statics back to power-on between scenarios (fw_unit.c puts
 * them in __fwdata/__fwbss, as the fuzz harness does). */
#include <mach-o/getsect.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
static uint8_t      *sec_p[2];
static unsigned long sec_n[2];
static uint8_t      *sec_saved[2];
__attribute__((no_sanitize("address"))) static void raw_copy(volatile uint8_t *d, const volatile uint8_t *s, unsigned long n) {
    for (unsigned long i = 0; i < n; i++) d[i] = s[i];
}
static void fw_sections_init(void) {
    const struct mach_header_64 *mh = (const struct mach_header_64 *)_dyld_get_image_header(0);
    static const char *names[2]     = {"__fwdata", "__fwbss"};
    for (int i = 0; i < 2; i++) {
        sec_p[i] = getsectiondata(mh, "__DATA", names[i], &sec_n[i]);
        if (sec_p[i] && sec_n[i]) {
            sec_saved[i] = malloc(sec_n[i]);
            raw_copy(sec_saved[i], sec_p[i], sec_n[i]);
        }
    }
    if (!sec_p[1] || !sec_n[1]) { fprintf(stderr, "no __fwbss\n"); abort(); }
}
static void fw_restore(void) {
    for (int i = 0; i < 2; i++)
        if (sec_saved[i]) raw_copy(sec_p[i], sec_saved[i], sec_n[i]);
}

static int failures;
#define CHECK(cond, ...)                                                   \
    do {                                                                   \
        if (!(cond)) {                                                     \
            failures++;                                                    \
            fprintf(stderr, "  CHECK FAILED %s:%d: ", __FILE__, __LINE__); \
            fprintf(stderr, __VA_ARGS__);                                  \
            fprintf(stderr, "\n");                                         \
        }                                                                  \
    } while (0)

static const char *st_name(int s) {
    static const char *n[] = {"IDLE", "LINKING", "PAIRING", "CONNECTED", "REJECTED"};
    return (s >= 0 && s <= 4) ? n[s] : "?";
}

/* ---- the module's frames ---------------------------------------------------- */
static void frame(uint8_t t, uint8_t d, uint32_t gap_us) {
    sim_wire_push(t, gap_us);
    sim_wire_push(d, 0);
    sim_wire_push((uint8_t)(t + d), 0);
}
static void led_change(uint8_t bits) {   /* every change three times, 0-5 ms apart */
    frame(0x5A, bits, 200);
    frame(0x5A, bits, 2000);
    frame(0x5A, bits, 2000);
}

/* ---- the main loop ------------------------------------------------------------ */
static void run_ms(uint32_t ms) {
    uint64_t end = S.T + MS_TICKS(ms);
    while (S.T < end) {
        sim_advance(MS_TICKS(3));   /* ~335 Hz main loop */
        bluetooth_task();
    }
}

/* The peer answers A6 53 with a 5C (the board's battery poll), as on the wire. */
static uint32_t polls_seen;
static void module_answers_polls(void) {
    /* peer_last_a6 holds the last A6 parameter the module received */
    if (S.peer_last_a6 == 0x53) {
        S.peer_last_a6 = 0;
        polls_seen++;
        frame(0x5C, 80, 1500);
    }
}

static void run_ms_with_module(uint32_t ms) {
    uint64_t end = S.T + MS_TICKS(ms);
    uint64_t next23 = S.T + MS_TICKS(4000);
    while (S.T < end) {
        sim_advance(MS_TICKS(3));
        bluetooth_task();
        module_answers_polls();
        if (S.T >= next23) {   /* the module's periodic, state-free 5B 23 */
            frame(0x5B, 0x23, 100);
            next23 = S.T + MS_TICKS(4000);
        }
    }
}

static void key_tap(uint8_t kc) {
    report_keyboard_t r = {0};
    r.keys[0] = kc;
    bluetooth_send_keyboard(&r);
    run_ms_with_module(30);
    memset(&r, 0, sizeof r);
    bluetooth_send_keyboard(&r);
    run_ms_with_module(30);
}

/* ---- the deep sleep, as sleep.c sequences it ---------------------------------- */
static uint64_t sleep_t0;
static void run_ms_with_module(uint32_t ms);
static void deep_sleep_enter(void) {
    /* sleep_task() re-checks the blockers every pass: DSB_TX waits for idle. */
    for (int i = 0; i < 1000 && !ch582_tx_idle(); i++) run_ms_with_module(3);
    if (!ch582_tx_idle()) SIM_FAIL("sleep admission: TX never idle (DSB_TX would block)");
    if (ch582_is_pairing()) SIM_FAIL("sleep admission: pairing (DSB_PAIRING would block)");
    S.rx_off = true;
    sleep_t0 = S.T;
}
/* While asleep: the line keeps delivering (into a receiver that is off). */
static void asleep_ms(uint32_t ms) {
    sim_advance(MS_TICKS(ms));
}
static void deep_sleep_exit(void) {
    uint32_t slept_ms = (uint32_t)((S.T - sleep_t0) * 2u / 375u);
    S.ms_off -= slept_ms;          /* QMK's timer stood still asleep */
    S.rx_off = false;
    SD2.iqueue.count = 0;          /* iqResetI(&SD2.iqueue) */
    SD2.iqueue.head  = 0;
    ch582_rx_resync();             /* sleep.c:614 */
    ch582_sleep_wake();            /* recovery_begin(), sleep.c:676 */
}

/* ---- the scenarios -------------------------------------------------------------- */
static void boot_and_connect(void) {
    fw_restore();
    polls_seen = 0;
    sim_reset();
    sim_verbose   = 0;
    S.ms_off      = 50000;   /* well past boot */
    S.peer_ack    = true;
    S.peer_ack_us = 4000;
    bluetooth_init();
    ch582_set_profile(CH582_PROFILE_BT_1);   /* the slider on BT, slot 1 */
    run_ms_with_module(200);
    frame(0x5B, 0x33, 500);                  /* attempting */
    run_ms_with_module(300);
    frame(0x5B, 0x32, 500);                  /* linked */
    led_change(0x02);                        /* the host's on-connect LED report: Caps on */
    run_ms_with_module(500);
}

static void report(const char *tag) {
    fw_view_t v;
    fw_snapshot(&v);
    printf("    %-34s conn_state=%-9s is_connected=%d host_leds=0x%02x host_kbd_reports=%u polls=%u\n", tag,
           st_name(v.conn_state), v.is_connected, v.host_leds, S.host_kbd_n, polls_seen);
}

typedef enum { HOST_RETURNS_WHILE_ASLEEP, HOST_RETURNS_WHILE_AWAKE } when_t;

/* LINKING at sleep entry; the module re-links (5B 32 + the host's LED report)
 * while the receiver is off; a key wakes the board; the host's lock state never
 * changes afterwards. */
static int scenario_linking(when_t when, bool led_change_later) {
    boot_and_connect();
    report("connected");
    CHECK(ch582_get_conn_state() == CH582_CONN_CONNECTED, "setup: expected CONNECTED");

    /* The host leaves (lid closed, out of range): the module says attempting. */
    frame(0x5B, 0x33, 500);
    run_ms_with_module(20000);   /* the board idles toward its ladder sleep */
    report("host gone, awake");
    CHECK(ch582_get_conn_state() == CH582_CONN_LINKING, "expected LINKING after 5B 33");
    /* The fix's blocker: the attempt is 20 s old, so sleep.c holds the sleep
     * off until 60 s; then it lets go. */
    CHECK(ch582_linking_recent(), "the attempt at 20 s should hold off the sleep");
    run_ms_with_module(41000);
    CHECK(!ch582_linking_recent(), "the attempt at 61 s should no longer hold off the sleep");
    CHECK(!ch582_link_state_stale(), "awake, the state is not stale");

    if (when == HOST_RETURNS_WHILE_ASLEEP) {
        deep_sleep_enter();
        asleep_ms(60000);
        /* The host comes back; the module, still trying on its own
         * (DEEP-SLEEP-BUILD-PLAN.md: "the module keeps trying on its own"),
         * re-links. Its one `5B 32` and the host's LED restore are sent
         * while the receiver is off. */
        frame(0x5B, 0x32, 500);
        led_change(0x02);
        asleep_ms(120000);
        ch582_conn_state_t before = ch582_get_conn_state();
        deep_sleep_exit();
        CHECK(ch582_get_conn_state() == before, "ch582_sleep_wake changed conn_state");
        CHECK(ch582_link_state_stale(), "after the sleep the state should read stale");
        report("woken (no main loop yet)");
    } else {
        /* Control: the same frames with the board awake. */
        frame(0x5B, 0x32, 500);
        led_change(0x02);
        run_ms_with_module(1000);
    }

    /* The waking key, then the battery poll released after it (sleep.c step 5). */
    key_tap(0x04);
    if (when == HOST_RETURNS_WHILE_ASLEEP) ch582_battery_poll_release();
    /* Ten minutes of typing; the module's 5B 23 and 5C keep coming. */
    for (int i = 0; i < 600; i++) {
        key_tap((uint8_t)(0x04 + (i % 20)));
        run_ms_with_module(940);
    }
    report("after 10 min of typing");
    int st = ch582_get_conn_state();

    if (led_change_later) {
        /* Caps pressed on the host: a CHANGE, so the module forwards it. */
        led_change(0x00);
        run_ms_with_module(500);
        report("after a Caps change");
    }
    return st;
}

/* REJECTED at sleep entry (5B 36 persists), then a re-link while asleep. */
static int scenario_rejected(bool led_change_later) {
    boot_and_connect();
    frame(0x5B, 0x33, 500);
    run_ms_with_module(2000);
    frame(0x5B, 0x33, 500);
    run_ms_with_module(2000);
    frame(0x5B, 0x36, 500);
    frame(0x5B, 0x23, 3000);
    run_ms_with_module(20000);
    report("attempt abandoned, awake");
    CHECK(ch582_get_conn_state() == CH582_CONN_REJECTED, "expected REJECTED after 5B 36");
    CHECK(!ch582_linking_recent(), "REJECTED holds off no sleep");

    deep_sleep_enter();
    asleep_ms(60000);
    frame(0x5B, 0x32, 500);
    led_change(0x02);
    asleep_ms(60000);
    deep_sleep_exit();

    key_tap(0x04);
    ch582_battery_poll_release();
    for (int i = 0; i < 300; i++) {
        key_tap((uint8_t)(0x04 + (i % 20)));
        run_ms_with_module(940);
    }
    report("after 5 min of typing");
    CHECK(ch582_get_conn_state() == CH582_CONN_REJECTED && ch582_link_state_stale(),
          "D: still REJECTED, read stale (the band names no remedy)");
    if (led_change_later) {
        led_change(0x00);
        run_ms_with_module(200);
        led_change(0x02);
        run_ms_with_module(500);
        report("after two Caps changes");
    }
    return ch582_get_conn_state();
}

/* The module cycling its attempts (unmeasured on the wire; the capture saw it
 * give up after one round): every 20 s a 36 and the next 33 back to back, in
 * one main-loop pass, so no pass between them sees REJECTED and admits the
 * sleep. Its own attempts hold the sleep off once between wakes; a wake
 * re-arms that, and a select of the board's own always holds. Returns the
 * seconds held of the 10 min. */
static unsigned held_s(unsigned seconds, bool cycle_every_20s) {
    unsigned held = 0;
    for (unsigned s = 1; s <= seconds; s++) {
        run_ms_with_module(1000);
        if (cycle_every_20s && s % 20 == 0) {
            frame(0x5B, 0x36, 500);
            frame(0x5B, 0x33, 300);
        }
        if (ch582_linking_recent()) held++;
    }
    return held;
}

static void scenario_cycle(void) {
    boot_and_connect();
    frame(0x5B, 0x33, 500);   /* the host leaves: the module's first attempt since boot */
    unsigned held = held_s(600, true);
    report("10 min of 33, 36+33 every 20 s");
    CHECK(ch582_get_conn_state() == CH582_CONN_LINKING, "E: expected LINKING, got %s", st_name(ch582_get_conn_state()));
    CHECK(held <= 61, "E: the module's attempts held the sleep off %u s of 600 (want the first 60 s only)", held);
    CHECK(!ch582_linking_recent(), "E: at 10 min the cycle should hold nothing");

    deep_sleep_enter();
    asleep_ms(60000);
    deep_sleep_exit();
    frame(0x5B, 0x36, 500);
    frame(0x5B, 0x33, 300);
    run_ms_with_module(1000);
    CHECK(ch582_linking_recent(), "E: the first attempt after a wake should hold again");
    held = held_s(120, true);
    CHECK(held <= 60, "E: after the wake, held %u s of 120 (want under a minute)", held);

    ch582_set_profile(CH582_PROFILE_BT_1);   /* a slot key: the board's own select */
    run_ms_with_module(1000);
    CHECK(ch582_linking_recent(), "E: a select of the board's own should always hold");
    run_ms_with_module(60000);
    CHECK(!ch582_linking_recent(), "E: and lets go at 60 s");
}

int main(void) {
    fw_sections_init();
    printf("A. LINKING at sleep, the module re-links while asleep, no lock change after:\n");
    int a = scenario_linking(HOST_RETURNS_WHILE_ASLEEP, false);
    CHECK(a == CH582_CONN_LINKING, "A: nothing tells the board: still LINKING, got %s", st_name(a));
    CHECK(ch582_link_state_stale(), "A: the state should still read stale (no 5B 31-36 since)");
    CHECK(S.host_kbd_n > 1000, "A: keys should reach the host (A1 is not gated), got %u", S.host_kbd_n);

    printf("B. Control: the same re-link with the board awake:\n");
    int b = scenario_linking(HOST_RETURNS_WHILE_AWAKE, false);
    CHECK(b == CH582_CONN_CONNECTED, "B: expected CONNECTED, got %s", st_name(b));
    CHECK(ch582_get_host_leds() == 0x02, "B: expected host_leds 0x02");
    CHECK(!ch582_link_state_stale(), "B: never slept, not stale");

    printf("C. As A, then the host's Caps changes once (the promotion's fresh 5A):\n");
    scenario_linking(HOST_RETURNS_WHILE_ASLEEP, true);
    CHECK(ch582_get_conn_state() == CH582_CONN_CONNECTED, "C: a changed 5A should promote, got %s",
          st_name(ch582_get_conn_state()));
    CHECK(ch582_get_host_leds() == 0x00, "C: the 2nd/3rd copy should set host_leds");
    CHECK(!ch582_link_state_stale(), "C: the promotion makes the state current");

    printf("D. REJECTED at sleep, a re-link while asleep, then two Caps changes:\n");
    int d = scenario_rejected(true);
    CHECK(d == CH582_CONN_CONNECTED, "D: the promotion from REJECTED should recover, got %s", st_name(d));
    CHECK(ch582_get_host_leds() == 0x02, "D: host_leds should follow the host (Caps on), got 0x%02x", ch582_get_host_leds());
    CHECK(!ch582_link_state_stale(), "D: the promotion makes the state current");

    printf("E. The module cycling 36 and 33 back to back for 10 min, no input:\n");
    scenario_cycle();

    printf("\n%s (%d check(s) failed)\n", failures ? "RESULT: FAIL" : "RESULT: PASS", failures);
    return failures ? 1 : 0;
}
