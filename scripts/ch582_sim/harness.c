/* Host harness for the CH582F driver's transport counters (Phase 1b, D1).
 *
 * ch582f_ajazz.c is compiled VERBATIM against the stubs here, with the daily
 * build's flags (RAW_ENABLE; no CONSOLE_ENABLE, no WDT_TEST_HOOKS), so no test
 * hook enters either firmware build and no flash is needed to check how each
 * way of losing a frame is counted. One case per process, because the
 * driver's state is file-static. Build and run everything with run.sh.
 *
 * The world: a millisecond clock, a UART whose writes are recorded and whose
 * reads come from a buffer the case fills (ACKs are `61 0D 0A`), and the
 * serial driver's error flags. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hal.h"
#include "quantum.h"
#include "ch582f_ajazz.h"

SerialDriver SD2;

static uint32_t now_ms = 1;
uint16_t timer_read(void) { return (uint16_t)now_ms; }
uint16_t timer_elapsed(uint16_t last) { return (uint16_t)((uint16_t)now_ms - last); }
uint32_t timer_read32(void) { return now_ms; }
uint32_t timer_elapsed32(uint32_t last) { return now_ms - last; }

/* Every frame written, in order. */
#define WR_MAX 256
static uint8_t wr[WR_MAX][20];
static uint8_t wr_len[WR_MAX];
static int     wr_n;
void   sdStart(SerialDriver *sd, const SerialConfig *cfg) { (void)sd; (void)cfg; }
size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n) {
    (void)sd;
    if (wr_n < WR_MAX) {
        memcpy(wr[wr_n], b, n < 20 ? n : 20);
        wr_len[wr_n++] = (uint8_t)n;
    }
    return n;
}

static uint8_t rx[512];
static int     rx_head, rx_tail;
static void    rx_feed(const uint8_t *b, int n) { for (int i = 0; i < n; i++) rx[rx_tail++ % 512] = b[i]; }
static void    rx_ack(void) { static const uint8_t a[3] = {0x61, 0x0D, 0x0A}; rx_feed(a, 3); }
size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, int timeout) {
    (void)sd; (void)n; (void)timeout;
    if (rx_head == rx_tail) return 0;
    *b = rx[rx_head++ % 512];
    return 1;
}

static event_source_t es;
static eventflags_t   uart_flags;
event_source_t *chnGetEventSource(SerialDriver *sd) { (void)sd; return &es; }
void chEvtRegisterMaskWithFlags(event_source_t *s, event_listener_t *el, eventmask_t m, eventflags_t f) {
    (void)s; (void)el; (void)m; (void)f;
}
eventflags_t chEvtGetAndClearFlags(event_listener_t *el) {
    (void)el;
    eventflags_t f = uart_flags;
    uart_flags     = 0;
    return f;
}

static int rx_malformed;
void health_note_rx_malformed(void) { rx_malformed++; }
/* D2's profile (flash 1c): the simulated system tick, and a 5C hook whose cost
 * the case sets -- the stand-in for battery_5c_report's trimmed-mean sort. */
bool            loop_acct_on = true;
static uint16_t tick;
static uint16_t c5_cost;
uint16_t        sim_tick(void) { return tick; }
void battery_5c_report(uint8_t pct) { (void)pct; tick = (uint16_t)(tick + c5_cost); }
void send_raw_hid(uint8_t *data, uint8_t length) { (void)data; (void)length; }

static int failures;
#define CHECK(cond, ...)                                          \
    do {                                                          \
        if (!(cond)) {                                            \
            failures++;                                           \
            printf("  FAIL line %d (t=%u ms): ", __LINE__, now_ms); \
            printf(__VA_ARGS__);                                  \
            printf("\n");                                         \
        }                                                         \
    } while (0)

static ch582_link_stats_t st(void) {
    ch582_link_stats_t s;
    ch582_link_stats(&s);
    return s;
}

static void run_ms(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i++) {
        ch582_task();
        now_ms++;
    }
}

static void key(uint8_t k) {
    report_keyboard_t r = {0};
    r.keys[0] = k;
    ch582_send_keyboard_report(&r);   /* an 0xA1 state frame */
}

static void poll(void) { uint8_t p = 0x53; ch582_send_command(0xA6, &p, 1); }   /* never coalesced */

/* One frame, every ACK withheld: 8 retransmits, then the driver gives up.
 * Nine ACK timeouts (CH582_TX_MAX_RETRIES is 8: the ninth gives up). */
static void withheld(void) {
    key(0x04);
    run_ms(2000);   /* < 5 s: no battery poll or stat line joins in */
    ch582_link_stats_t s = st();
    CHECK(s.giveups == 1, "retry exhaustion +1: %u", s.giveups);
    CHECK(s.timeouts == 9, "timeouts +9: %u", s.timeouts);
    CHECK(s.queue_full == 0, "queue-full +0: %u", s.queue_full);
    CHECK(s.replaced == 0, "replacements +0: %u", s.replaced);
    CHECK(wr_n == 9, "the frame went out 9 times (1 + 8 retransmits): %d writes", wr_n);
}

/* The queue filled with non-state frames: the next one is refused. The ring
 * holds CH582_TXQ_LEN - 1 = 23. */
static void queue_full(void) {
    for (int i = 0; i < 23; i++) poll();
    CHECK(st().queue_full == 0, "23 fit: %u refused", st().queue_full);
    poll();
    ch582_link_stats_t s = st();
    CHECK(s.queue_full == 1, "queue-full +1: %u", s.queue_full);
    CHECK(s.giveups == 0, "retry exhaustion +0: %u", s.giveups);
    CHECK(s.replaced == 0, "replacements +0 (0xA6 is never coalesced): %u", s.replaced);
}

/* Fill the queue to `used` frames, the head in flight. */
static void in_flight_then(uint8_t head_cmd, bool a1_behind, int used) {
    if (head_cmd == 0xA1) key(0x10); else poll();
    run_ms(1);                       /* the pump sends it: now in flight */
    int n = 1;
    if (a1_behind) { key(0x04); n++; }
    while (n < used) { poll(); n++; }
}

/* Drain: ACK every frame and collect the 0xA1 frames that go out after the
 * setup's first write. */
static int drain_a1(uint8_t *keys_out, int max) {
    int from = wr_n, got = 0;
    for (int i = 0; i < 40; i++) {
        rx_ack();
        run_ms(2);
    }
    for (int i = from; i < wr_n; i++)
        if (wr[i][0] == 0xA1 && got < max) keys_out[got++] = wr[i][3];
    return got;
}

/* The queue nearly full (>= 20 of 24) with an 0xA1 queued behind the in-flight
 * frame: another 0xA1 overwrites it, so only the newest state goes out. */
static void replaced(void) {
    in_flight_then(0xA6, true, 20);
    key(0x05);
    ch582_link_stats_t s = st();
    CHECK(s.replaced == 1, "replacements +1: %u", s.replaced);
    CHECK(s.queue_full == 0, "queue-full +0: %u", s.queue_full);
    uint8_t keys[8];
    int n = drain_a1(keys, 8);
    CHECK(n == 1 && keys[0] == 0x05, "one 0xA1 goes out, carrying the newer state: %d frames, first key %02X", n,
          n ? keys[0] : 0);
}

/* Nearly full, but no earlier 0xA1 behind the head: appended, not replaced. */
static void not_replaced_none_behind(void) {
    in_flight_then(0xA6, false, 20);
    key(0x05);
    ch582_link_stats_t s = st();
    CHECK(s.replaced == 0, "nothing to replace: %u", s.replaced);
    CHECK(s.queue_full == 0, "appended: queue-full %u", s.queue_full);
}

/* Nearly full, the only 0xA1 is the in-flight head: never touched. */
static void not_replaced_head(void) {
    in_flight_then(0xA1, false, 20);
    key(0x05);
    ch582_link_stats_t s = st();
    CHECK(s.replaced == 0, "the in-flight frame is never overwritten: %u", s.replaced);
    uint8_t keys[8];
    int n = drain_a1(keys, 8);
    CHECK(n == 1 && keys[0] == 0x05, "the new state is appended and sent: %d frames", n);
}

/* UART error flags are counted in the daily build (they were console-only). */
static void uart_errors(void) {
    uart_flags = SD_OVERRUN_ERROR | SD_FRAMING_ERROR;
    run_ms(1);
    uart_flags = SD_PARITY_ERROR;
    run_ms(1);
    ch582_link_stats_t s = st();
    CHECK(s.uart_overrun == 1 && s.uart_framing == 1 && s.uart_parity == 1, "uart ovr %u fe %u pe %u",
          s.uart_overrun, s.uart_framing, s.uart_parity);
}

/* A slow 5C hook makes a slow call, recorded with its section split; a cheap
 * one is not recorded; with the flag off nothing is. Then the pages, as hex
 * for run.sh's decode check. */
static void dump_pages(void) {
    for (uint8_t pg = 0x21; pg <= 0x2A; pg++) {
        uint8_t out[28];
        if (!ch582_prof_fill(pg, out)) continue;
        printf("PAGE %u ", pg);
        for (int i = 0; i < 28; i++) printf("%02x", out[i]);
        printf("\n");
    }
}
static void profile(void) {
    static const uint8_t c5[3] = {0x5C, 47, (uint8_t)(0x5C + 47)};
    uint8_t out[28];
    c5_cost = 100;                    /* 0.53 ms: not slow */
    rx_feed(c5, 3); run_ms(1);
    ch582_prof_fill(0x21, out);
    CHECK(out[0] == 0, "a cheap call is not recorded: %u", out[0]);
    c5_cost = 900;                    /* 4.8 ms: slow */
    rx_feed(c5, 3); rx_feed(c5, 3); run_ms(1);
    ch582_prof_fill(0x21, out);
    uint32_t calls = out[0] | out[1] << 8, c5t = out[12] | out[13] << 8 | out[14] << 16;
    CHECK(calls == 1 && c5t == 1800, "one slow call, 2 x 900 ticks in the 5C hook: %u %u", calls, c5t);
    ch582_prof_fill(0x22, out);
    uint32_t n5c = out[0] | out[1] << 8, hookt = out[4] | out[5] << 8;
    uint16_t mx = out[8] | out[9] << 8;
    CHECK(n5c == 3 && hookt == 1900 && mx == 900 && out[11] == 8 && (out[12] | out[13] << 8) == 750,
          "every report counted (%u), hook ticks %u, longest %u, ring %u, threshold %u", n5c, hookt, mx, out[11],
          out[12] | out[13] << 8);
    ch582_prof_fill(0x23, out);
    uint16_t total = out[4] | out[5] << 8, sc5 = out[10] | out[11] << 8;
    CHECK(total == 1800 && sc5 == 1800 && out[16] == 6 && out[17] == 2,
          "ring 0: total %u, 5C %u, %u bytes, %u reports", total, sc5, out[16], out[17]);
    loop_acct_on = false;             /* off: nothing is timed or recorded */
    rx_feed(c5, 3); run_ms(1);
    ch582_prof_fill(0x21, out);
    CHECK(out[0] == 1, "off: still one slow call: %u", out[0]);
    loop_acct_on = true;
    CHECK(!ch582_prof_fill(0x20, out) && !ch582_prof_fill(0x2B, out) && !ch582_prof_fill(8, out),
          "pages outside 0x21-0x2A are refused");
    dump_pages();
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: harness CASE\n"); return 2; }
    const char *c = argv[1];
    if      (!strcmp(c, "withheld"))                 withheld();
    else if (!strcmp(c, "queue_full"))               queue_full();
    else if (!strcmp(c, "replaced"))                 replaced();
    else if (!strcmp(c, "not_replaced_none_behind")) not_replaced_none_behind();
    else if (!strcmp(c, "not_replaced_head"))        not_replaced_head();
    else if (!strcmp(c, "uart_errors"))              uart_errors();
    else if (!strcmp(c, "profile"))                  profile();
    else { fprintf(stderr, "unknown case %s\n", c); return 2; }
    printf("%s %s\n", failures ? "FAIL" : "ok  ", c);
    return failures ? 1 : 0;
}
