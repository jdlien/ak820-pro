/* The world around ch582f_ajazz.c, for the fuzz harness (harness.c):
 *   - one 64-bit tick at 187.5 kHz drives the ChibiOS system time (16-bit,
 *     CH_CFG_ST_RESOLUTION 16) and QMK's millisecond timer (with an offset the
 *     input picks, so the 16- and 32-bit wraps are reachable);
 *   - the UART2 line at 115200 8N1: bytes the module sends sit on a "wire"
 *     with a not-before time and land in the 128-byte input queue one byte
 *     time apart (a full queue drops the byte and raises SD_OVERRUN_ERROR, as
 *     hal_serial_lld.c's serve_interrupt does); the output queue moves into a
 *     16-byte hardware FIFO that drains at the same rate; sdWrite blocks, with
 *     the clock running, while the output queue is full (TIME_INFINITE);
 *   - virtual timers fire as the clock passes them (the r81 long clock's);
 *   - a peer (the CH582F) that reads what the board sends and, if the input
 *     says so, ACKs each frame `61 0D 0A` after a delay;
 *   - the board functions the driver calls: display text slot, rtc set,
 *     health, battery, watchdog breadcrumbs, the raw-HID leases and the VIA
 *     handler the radio's raw HID dispatches into. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "hal.h"
#include "sim.h"
#include "graphics/display.h"
#include "rtc/rtc.h"
#include "rtc/rtc_payload.h"
#include "ch582f_ajazz.h"

/* ---- time ------------------------------------------------------------------- */
#define BAUD        115200u
#define SUB_PER_TICK BAUD                        /* subticks: tick * 115200 */
#define BYTE_SUB    ((uint64_t)10u * 187500u)   /* one 10-bit character, in subticks */

sim_t S;
int sim_verbose;

static uint32_t ms_of(uint64_t t) { return (uint32_t)(t * 2u / 375u) + S.ms_off; }

uint32_t timer_read32(void) { if (S.auto_adv) sim_advance(S.auto_adv); return ms_of(S.T); }
uint16_t timer_read(void) { return (uint16_t)timer_read32(); }
uint16_t timer_elapsed(uint16_t last) { return (uint16_t)(timer_read() - last); }
uint32_t timer_elapsed32(uint32_t last) { return timer_read32() - last; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)(S.T + S.tick_off); }
sysinterval_t chVTTimeElapsedSinceX(systime_t start) { return (sysinterval_t)(chVTGetSystemTimeX() - start); }
uint32_t  st_lld_get_counter(void) { return (uint16_t)(S.T + S.tick_off); }
void wait_ms(uint32_t ms) {
    if (S.lock) SIM_FAIL("wait_ms with the system locked");
    sim_advance((uint64_t)ms * 375u / 2u);
}

/* ---- the lock ------------------------------------------------------------------ */
syssts_t chSysGetStatusAndLockX(void) { syssts_t s = S.lock; S.lock = 1; return s; }
void chSysRestoreStatusX(syssts_t sts) { S.lock = (int)sts; }
void chSysLock(void) {
    if (S.lock) SIM_FAIL("chSysLock nested");
    S.lock = 1;
}
void chSysUnlock(void) {
    if (!S.lock) SIM_FAIL("chSysUnlock unlocked");
    S.lock = 0;
}
void chSysLockFromISR(void) { if (!S.in_isr) SIM_FAIL("chSysLockFromISR outside an ISR"); }
void chSysUnlockFromISR(void) {}

/* ---- virtual timers ---------------------------------------------------------- */
#define VT_MAX 4
static virtual_timer_t *vts[VT_MAX];
void chVTObjectInit(virtual_timer_t *vtp) { memset(vtp, 0, sizeof *vtp); }
static void vt_arm(virtual_timer_t *vtp, sysinterval_t delay, vtfunc_t fn, void *par) {
    vtp->armed    = true;
    vtp->deadline = S.T + (delay ? delay : 1);
    vtp->fn       = fn;
    vtp->arg      = par;
    for (int i = 0; i < VT_MAX; i++) if (vts[i] == vtp) return;
    for (int i = 0; i < VT_MAX; i++) if (!vts[i]) { vts[i] = vtp; return; }
    SIM_FAIL("too many virtual timers");
}
void chVTSet(virtual_timer_t *vtp, sysinterval_t delay, vtfunc_t fn, void *par) {
    if (S.lock) SIM_FAIL("chVTSet locked");
    vt_arm(vtp, delay, fn, par);
}
void chVTSetI(virtual_timer_t *vtp, sysinterval_t delay, vtfunc_t fn, void *par) {
    if (!S.lock && !S.in_isr) SIM_FAIL("chVTSetI unlocked");
    vt_arm(vtp, delay, fn, par);
}

/* ---- the serial driver -------------------------------------------------------- */
SerialDriver SD2;
static event_source_t   es;
static event_listener_t *listener;

static void q_put(io_queue_t *q, uint8_t b) { q->buf[(q->head + q->count) % SERIAL_BUFFERS_SIZE] = b; q->count++; }
static uint8_t q_get(io_queue_t *q) { uint8_t b = q->buf[q->head]; q->head = (q->head + 1) % SERIAL_BUFFERS_SIZE; q->count--; return b; }

void sdStart(SerialDriver *sd, const SerialConfig *cfg) {
    (void)cfg;
    sd->started = true;
}

static void add_flags(eventflags_t f) {
    if (listener && listener->registered) listener->flags |= f;
}

static void peer_byte(uint8_t b);

static void tx_move_to_fifo(void) {
    while (SD2.oqueue.count && S.tx_fifo < 16) {
        uint8_t b = q_get(&SD2.oqueue);
        S.tx_fifo_buf[(S.tx_fifo_head + S.tx_fifo) % 16] = b;
        if (S.tx_fifo == 0 && S.tx_next_sub < S.T * SUB_PER_TICK) S.tx_next_sub = S.T * SUB_PER_TICK;
        if (S.tx_fifo == 0) S.tx_next_sub += BYTE_SUB;
        S.tx_fifo++;
    }
}

size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n) {
    if (sd != &SD2) SIM_FAIL("sdWrite to another driver");
    if (S.lock) SIM_FAIL("sdWrite with the system locked");
    if (S.in_isr) SIM_FAIL("sdWrite in an ISR");
    S.writes++;
    for (size_t i = 0; i < n; i++) {
        while (SD2.oqueue.count == SERIAL_BUFFERS_SIZE) {
            /* TIME_INFINITE: the caller waits for room, the clock running. */
            uint64_t next = S.tx_next_sub / SUB_PER_TICK + 1;
            S.blocked_ticks += next > S.T ? next - S.T : 1;
            sim_advance(next > S.T ? next - S.T : 1);
        }
        q_put(&SD2.oqueue, b[i]);
        tx_move_to_fifo();
    }
    return n;
}

size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, sysinterval_t timeout) {
    if (sd != &SD2) SIM_FAIL("read from another driver");
    if (timeout != TIME_IMMEDIATE) SIM_FAIL("a blocking read");
    if (S.lock) SIM_FAIL("read with the system locked");
    if (n == 0) SIM_FAIL("a zero-length read (would block forever in ChibiOS? no: returns 0)");
    size_t k = 0;
    while (k < n && SD2.iqueue.count) b[k++] = q_get(&SD2.iqueue);
    S.bytes_read += k;
    if (S.read_cost) sim_advance(S.read_cost * (k + 1));   /* the drain's own time: the line keeps delivering */
    return k;
}

size_t oqGetEmptyI(io_queue_t *q) {
    if (!S.lock) SIM_FAIL("oqGetEmptyI unlocked");
    return SERIAL_BUFFERS_SIZE - q->count;
}
size_t oqGetFullI(io_queue_t *q) {
    if (!S.lock) SIM_FAIL("oqGetFullI unlocked");
    return q->count;
}

event_source_t *chnGetEventSource(SerialDriver *sd) { (void)sd; return &es; }
void chEvtRegisterMaskWithFlags(event_source_t *s, event_listener_t *el, eventmask_t m, eventflags_t f) {
    (void)s; (void)m;
    el->registered = true;
    el->wflags     = f;
    el->flags      = 0;
    listener       = el;
}
eventflags_t chEvtGetAndClearFlags(event_listener_t *el) {
    eventflags_t f = el->flags;
    el->flags      = 0;
    return f & el->wflags;
}

void sim_uart_error(eventflags_t f) { add_flags(f); }

/* ---- the wire (module -> board) -----------------------------------------------
 * Two streams share the line: the input's bytes and the peer's ACKs. A stream
 * keeps the line while its next byte follows on without a gap (a frame is not
 * interleaved), otherwise the stream whose next byte can start first wins. */
static void wire_push_s(int st, uint8_t b, uint32_t gap_us) {
    if (S.wire_n[st] >= WIRE_MAX) return;   /* the input's own bound, not a board one */
    /* The gap is from the previous byte's start (or now): bytes pushed together
     * follow each other at the line rate plus their gaps. */
    uint64_t base = S.T * SUB_PER_TICK;
    if (S.wire_n[st]) {
        uint64_t prev = S.wire[st][(S.wire_head[st] + S.wire_n[st] - 1) % WIRE_MAX].not_before + BYTE_SUB;
        if (prev > base) base = prev;
    }
    uint64_t nb = base + (uint64_t)gap_us * 187500u * BAUD / 1000000u;
    wire_byte_t *w = &S.wire[st][(S.wire_head[st] + S.wire_n[st]) % WIRE_MAX];
    w->b          = b;
    w->err        = st == 0 ? S.pending_err : 0;
    if (st == 0) S.pending_err = 0;
    w->not_before = nb;
    S.wire_n[st]++;
}
void sim_wire_push(uint8_t b, uint32_t gap_us) { wire_push_s(0, b, gap_us); }
static void peer_push(uint8_t b, uint32_t gap_us) { wire_push_s(1, b, gap_us); }
void sim_wire_clear(void) { S.wire_n[0] = S.wire_n[1] = 0; }
int  sim_wire_pending(void) { return S.wire_n[0] + S.wire_n[1]; }

/* Which stream sends next, and when its byte completes (subticks); -1 if none. */
static int wire_pick(uint64_t *done) {
    uint64_t start[2];
    for (int st = 0; st < 2; st++) {
        if (!S.wire_n[st]) continue;
        const wire_byte_t *w = &S.wire[st][S.wire_head[st]];
        start[st] = S.rx_line_free > w->not_before ? S.rx_line_free : w->not_before;
    }
    int pick = -1;
    if (S.wire_n[S.wire_cur] && start[S.wire_cur] == S.rx_line_free) pick = S.wire_cur;   /* contiguous */
    else if (S.wire_n[0] && S.wire_n[1]) pick = start[1] < start[0] ? 1 : 0;
    else if (S.wire_n[0]) pick = 0;
    else if (S.wire_n[1]) pick = 1;
    if (pick >= 0) *done = start[pick] + BYTE_SUB;
    return pick;
}

static void rx_isr_byte(uint8_t b) {
    S.in_isr = 1;
    if (SD2.iqueue.count == SERIAL_BUFFERS_SIZE) {
        if (sim_verbose > 1) fprintf(stderr, "  [%9.3f ms] RX queue full, byte %02X dropped\n", S.T / 187.5, b);
        add_flags(SD_OVERRUN_ERROR);   /* iqPutI < MSG_OK */
        S.rx_dropped++;
    } else {
        q_put(&SD2.iqueue, b);
    }
    S.in_isr = 0;
}

void sim_advance(uint64_t dt) {
    uint64_t end = S.T + dt;
    for (;;) {
        uint64_t best = end * SUB_PER_TICK;
        int      what = 0;
        uint64_t wt;
        int      ws = wire_pick(&wt);
        if (ws >= 0 && wt <= best) { best = wt; what = 1; }
        if (S.tx_fifo && S.tx_next_sub <= best) { best = S.tx_next_sub; what = 2; }
        for (int i = 0; i < VT_MAX; i++) {
            if (vts[i] && vts[i]->armed && vts[i]->deadline * SUB_PER_TICK <= best) {
                best = vts[i]->deadline * SUB_PER_TICK;
                what = 3;
            }
        }
        uint64_t t_ticks = (best + SUB_PER_TICK - 1) / SUB_PER_TICK;
        if (t_ticks > S.T) S.T = t_ticks;
        if (what == 0) break;
        if (what == 1) {
            S.rx_line_free  = best;
            S.wire_cur      = ws;
            uint8_t b       = S.wire[ws][S.wire_head[ws]].b;
            uint8_t e       = S.wire[ws][S.wire_head[ws]].err;
            S.wire_head[ws] = (S.wire_head[ws] + 1) % WIRE_MAX;
            S.wire_n[ws]--;
            if (S.rx_off) continue;   /* the receiver is off (asleep): lost */
            if (e) add_flags(e);      /* set_error() before the byte is queued, as serve_interrupt does */
            rx_isr_byte(b);
        } else if (what == 2) {
            uint8_t b      = S.tx_fifo_buf[S.tx_fifo_head];
            S.tx_fifo_head = (S.tx_fifo_head + 1) % 16;
            S.tx_fifo--;
            if (S.tx_fifo) S.tx_next_sub += BYTE_SUB;
            tx_move_to_fifo();
            peer_byte(b);
        } else {
            for (int i = 0; i < VT_MAX; i++) {
                virtual_timer_t *v = vts[i];
                if (v && v->armed && v->deadline <= S.T) {
                    v->armed = false;
                    if (S.lock) SIM_FAIL("a timer interrupt would be masked here");
                    S.in_isr = 1;
                    v->fn(v, v->arg);
                    S.in_isr = 0;
                    break;
                }
            }
        }
    }
}

/* ---- the peer: the module's side of the TX line ------------------------------- */
static void peer_frame(const uint8_t *f, uint8_t n) {
    S.peer_frames++;
    if (sim_verbose > 1) { fprintf(stderr, "  [%9.3f ms] board->module:", S.T / 187.5); for (int i = 0; i < n && i < 12; i++) fprintf(stderr, " %02X", f[i]); fprintf(stderr, "\n"); }
    uint8_t s = 0;
    for (uint8_t i = 0; i < n - 1; i++) s += f[i];
    bool sum_ok = s == f[n - 1];
    if (!sum_ok) S.peer_badsum++;
    if (f[0] == 0xA1 && sum_ok) memcpy(S.host_kbd, &f[1], 8), S.host_kbd_n++;
    if (f[0] == 0xA6 && sum_ok) S.peer_last_a6 = f[1];
    if (f[0] == 0x91) {
        /* Raw HID over the dongle: a reply (status 0 only) then its receipt.
         * The receipt's own CRC must hold, and an OK receipt must carry the
         * CRC of the reply just before it. */
        if (!sum_ok) SIM_FAIL("a 91 frame with a bad sum");
        const uint8_t *p = &f[1];
        if (p[0] == 0xC7) {
            uint16_t c = 0xFFFF;
            for (int i = 0; i < 9; i++) {
                c ^= (uint16_t)(p[i] << 8);
                for (int k = 0; k < 8; k++) c = (uint16_t)((c & 0x8000u) ? (c << 1) ^ 0x1021u : c << 1);
            }
            if (c != (uint16_t)((p[9] << 8) | p[10])) SIM_FAIL("a receipt whose own CRC is wrong");
            if (p[4] == 0) {
                if (!S.have_reply) SIM_FAIL("an OK receipt with no reply before it");
                uint16_t r = 0xFFFF;
                for (int i = 0; i < 32; i++) {
                    r ^= (uint16_t)(S.last_reply[i] << 8);
                    for (int k = 0; k < 8; k++) r = (uint16_t)((r & 0x8000u) ? (r << 1) ^ 0x1021u : r << 1);
                }
                if (r != (uint16_t)((p[7] << 8) | p[8])) SIM_FAIL("an OK receipt naming another reply");
            }
            S.have_reply = false;
            S.receipts++;
        } else {
            if (S.have_reply) SIM_FAIL("two replies with no receipt between");
            memcpy(S.last_reply, p, 32);
            S.have_reply = true;
        }
    }
    bool ack = S.peer_ack && sum_ok && (f[0] != 0x91 || S.peer_ack91);
    if (ack) {
        uint32_t gap = S.peer_ack_us;
        peer_push(0x61, gap);
        peer_push(0x0D, 0);
        peer_push(0x0A, 0);
    }
}

static void peer_byte(uint8_t b) {
    if (S.peer_need == 0) {
        uint8_t need = b == 0xA1 ? 10 : b == 0xA3 ? 4 : b == 0xA6 ? 3 : b == 0x91 ? 34 : b == 0x61 ? 3 : 0;
        if (!need) { S.peer_junk++; return; }
        S.peer_need = need;
        S.peer_n    = 0;
    }
    S.peer_buf[S.peer_n++] = b;
    if (S.peer_n == S.peer_need) {
        S.peer_need = 0;
        if (S.peer_buf[0] == 0x61) {
            if (S.peer_buf[1] != 0x0D || S.peer_buf[2] != 0x0A) S.peer_junk++;
            S.board_acks++;
        } else {
            peer_frame(S.peer_buf, S.peer_n);
        }
    }
}

/* ---- board functions the driver calls ------------------------------------------- */
void health_note_rx_malformed(void) { S.rx_malformed++; }
void battery_5c_report(uint8_t pct) {
    if (pct > 100) SIM_FAIL("battery_5c_report(%u): over 100", pct);
    S.batt_reports++;
    S.batt_last = pct;
}

static int wdt_depth;
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return (uint32_t)wdt_depth++; }
void     watchdog_record_leave(uint32_t *previous) {
    if (wdt_depth <= 0 || (uint32_t)(wdt_depth - 1) != *previous) SIM_FAIL("unbalanced watchdog scope");
    wdt_depth--;
}
int sim_wdt_depth(void) { return wdt_depth; }

bool     loop_acct_on;
uint32_t loop_acct_run[16];
volatile uint8_t od_ctx;

void send_raw_hid(uint8_t *data, uint8_t length) { (void)data; (void)length; S.raw_hid_usb++; }

/* hid_protocol.c's leases (dev builds). */
bool hid_rawhid_media_within(uint32_t now, uint32_t ms) { return S.media_seen && now - S.media_at <= ms; }
bool hid_rawhid_clock_within(uint32_t s) { (void)s; return S.clock_owned; }

/* The radio's raw HID lands in the board's VIA handler (hid_protocol.c). Only
 * what the allow-list lets through is modelled, with the calls back into the
 * driver that the real handler makes for it. */
void via_custom_value_command_kb(uint8_t *data, uint8_t length) {
    if (length != 32) SIM_FAIL("via handler length %u", length);
    S.via_calls++;
    if (data[0] != 0x07) SIM_FAIL("dispatched a non-0x07 command");
    if (data[1] == 0x12) {
        if (data[2] < 1 || data[2] > 4) SIM_FAIL("dispatched a text sub-command off the allow-list");
        S.media_at   = timer_read32();
        S.media_seen = true;
#ifdef AK820_DEV_HOOKS
        ch582_lockchan_rawhid();
#endif
        if (data[2] == 2) display_clear_text();
    } else if (data[1] == 0x13) {
        switch (data[2]) {
            case 0x0E:
                if (data[3] == 0) {
                    ch582_link_stats_t ls;
                    ch582_link_stats(&ls);
                    memcpy(&data[4], &ls, 28);
                } else if (!ch582_prof_fill(data[3], &data[4])) {
                    SIM_FAIL("allowed HC_LINK page 0x%02x the driver refuses", data[3]);
                }
                break;
            case 0x02:
                data[3] = (uint8_t)ch582_get_conn_state();
                data[4] = ch582_get_target_slot();
                data[5] = ch582_get_battery();
                break;
            case 0x01: case 0x04: case 0x06: case 0x07: {
                uint32_t a, b, c;
                ch582_tx_stats(&a, &b, &c);
                memcpy(&data[4], &a, 4);
                break;
            }
            default: SIM_FAIL("dispatched a health sub-command off the allow-list");
        }
    } else {
        SIM_FAIL("dispatched channel 0x%02x", data[1]);
    }
}

/* ---- the display's text slot (display.c's contract, no drawing) ---------------- */
static char     text_buf[2][DISPLAY_TEXT_MAX + 1];
static uint8_t  text_icon;
static bool     text_present;
static uint32_t text_stamp;
#define TEXT_TIMEOUT_MS 180000u

void display_set_text_line(uint8_t line, uint8_t icon, const char *s, uint8_t len) {
    if (line >= 2) return;
    uint8_t max = line == 0 ? DISPLAY_TEXT_MAX_L0 : DISPLAY_TEXT_MAX_L1;
    if (len > max) SIM_FAIL("set_text_line(%u) len %u over the line's %u: the driver promised whole lines", line, len, max);
    uint8_t n = 0;
    for (uint8_t i = 0; i < len && s[i]; i++) {
        char c = s[i];
        if (c < 0x20 || c > 0x7E) SIM_FAIL("unprintable byte 0x%02x reached the text slot", (uint8_t)c);
        text_buf[line][n++] = c;
    }
    text_buf[line][n] = '\0';
    if (line == 0) text_icon = icon <= DISPLAY_ICON_STOP ? icon : DISPLAY_ICON_NONE;
    text_present = text_buf[0][0] || text_buf[1][0] || text_icon != DISPLAY_ICON_NONE;
    text_stamp   = timer_read32();
    S.text_sets++;
}
void display_set_text_icon(uint8_t icon) {
    if (!text_present) return;
    text_icon    = icon <= DISPLAY_ICON_STOP ? icon : DISPLAY_ICON_NONE;
    text_present = text_buf[0][0] || text_buf[1][0] || text_icon != DISPLAY_ICON_NONE;
}
void display_clear_text(void) {
    text_buf[0][0] = text_buf[1][0] = '\0';
    text_icon    = DISPLAY_ICON_NONE;
    text_present = false;
    S.text_clears++;
}
uint32_t display_text_lease_left(void) {
    if (!text_present) return 0;
    uint32_t age = timer_elapsed32(text_stamp);
    return age >= TEXT_TIMEOUT_MS ? 0 : TEXT_TIMEOUT_MS - age;
}
uint8_t display_get_text_line(uint8_t line, char *out, uint8_t max, uint8_t *icon, bool *present) {
    if (icon) *icon = text_icon;
    if (present) *present = text_present;
    if (!out || max == 0) return 0;
    out[0] = '\0';
    if (line >= 2) return 0;
    uint8_t n = 0;
    while (n + 1u < max && text_buf[line][n]) { out[n] = text_buf[line][n]; n++; }
    out[n] = '\0';
    return n;
}
void display_set_playback(uint8_t state, uint16_t pos, uint16_t dur) {
    if (state > 1) SIM_FAIL("playback state %u", state);
    S.pb_sets++;
    S.pb_pos = pos; S.pb_dur = dur; S.pb_state = state;
}
void display_set_playback_for(uint8_t state, uint16_t pos, uint16_t dur, uint32_t timeout_ms) {
    if (state > 1) SIM_FAIL("playback state %u", state);
    if (dur && pos > dur) SIM_FAIL("playback pos %u past dur %u", pos, dur);
    if (timeout_ms == 0 || timeout_ms > 135000u) SIM_FAIL("playback timeout %u", timeout_ms);
    S.pb_sets++;
    S.pb_pos = pos; S.pb_dur = dur; S.pb_state = state;
}

/* ---- the RTC (rtc.c's rtc_set_time_ms contract) -------------------------------- */
uint8_t rtc_set_time_ms(const rtc_time_t *t, uint16_t ms, uint8_t flags, int16_t bias_ppm, int16_t *offset_before) {
    if (t->year < 2026 || t->year > 2098 || t->month < 1 || t->month > 12 || t->day < 1 ||
        t->day > rtc_days_in_month(t->year, t->month) || t->weekday > 6 || t->hours > 23 || t->minutes > 59 ||
        t->seconds > 59 || ms > 999)
        SIM_FAIL("rtc_set_time_ms with an invalid time %u-%u-%u wd%u %u:%u:%u.%u", t->year, t->month, t->day,
                 t->weekday, t->hours, t->minutes, t->seconds, ms);
    if (flags & ~(RTC_SETF_FRAME)) SIM_FAIL("rtc flags 0x%02x", flags);
    if (bias_ppm != 0x7FFF) SIM_FAIL("bias %d", bias_ppm);
    S.rtc_sets++;
    if (offset_before) *offset_before = (int16_t)(S.rtc_sets * 7);
    static const uint8_t st[4] = {RTC_SET_STEPPED, RTC_SET_SLEWING, RTC_SET_RETRY, RTC_SET_REJECT};
    return st[S.rtc_status & 3];
}
void rtc_frame_trim_stats(uint16_t *trims, uint16_t *period) { *trims = 0; *period = 0; }

/* ---- reset ------------------------------------------------------------------------ */
void sim_reset(void) {
    memset(&S, 0, offsetof(sim_t, wire));
    memset(&SD2, 0, sizeof SD2);
    memset(vts, 0, sizeof vts);
    listener  = NULL;
    wdt_depth = 0;
    memset(text_buf, 0, sizeof text_buf);
    text_icon = 0; text_present = false; text_stamp = 0;
    loop_acct_on = false;
    memset(loop_acct_run, 0, sizeof loop_acct_run);
}
