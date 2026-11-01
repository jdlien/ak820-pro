/* verify-044: does the TX queue's near-full coalescing move a key report queued
 * AFTER a slot select to BEFORE it (onto the old host's link)?
 *
 * Compiles the firmware's ch582f_ajazz.c verbatim (#included by absolute path,
 * daily build: no AK820_DEV_HOOKS / CONSOLE_ENABLE). Time is simulated; the
 * module is modelled as: every frame written on the wire is ACKed (61 0D 0A)
 * ACK_DELAY_MS later while `acking`, or not at all while stalled. A "host
 * link" model applies each A1 on the wire to the slot the module is on (the
 * last A6 30..35 seen on the wire), so we can print what each host was left
 * with.
 *
 * Scenario A (the finding's trigger): slot 1, ACKs stall while typing at
 * ~100 wpm until the queue holds >= 20 frames, all keys released (queued);
 * Fn+W = ch582_set_profile(BT_2); 'a' pressed 100 ms later; ACKs resume;
 * 'a' released after the queue drains.
 * Scenario B (control): the same, but the select is made with the queue
 * nearly empty, so coalescing cannot engage. */
#include FW_CH582_C
#undef printf  /* the stub quantum.h silences printf for the driver, as the daily build does */

#include <stdio.h>
#include <stdlib.h>

/* ---- simulated clock ---- */
static uint64_t now_us;
uint16_t  timer_read(void) { return (uint16_t)(now_us / 1000); }
uint16_t  timer_elapsed(uint16_t last) { return (uint16_t)(timer_read() - last); }
uint32_t  timer_read32(void) { return (uint32_t)(now_us / 1000); }
uint32_t  timer_elapsed32(uint32_t last) { return timer_read32() - last; }
void      wait_ms(uint32_t ms) { now_us += (uint64_t)ms * 1000; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)(now_us * 3 / 16); } /* 187.5 kHz */
sysinterval_t chVTTimeElapsedSinceX(systime_t s) { return (sysinterval_t)(chVTGetSystemTimeX() - s); }
uint32_t  st_lld_get_counter(void) { return chVTGetSystemTimeX(); }

/* ---- the link ---- */
SerialDriver SD2;
void sdStart(SerialDriver *sd, const SerialConfig *cfg) { (void)sd; (void)cfg; }

#define RXCAP 4096
static uint8_t  rxbuf[RXCAP];
static size_t   rx_r, rx_w;
static bool     acking = true;
#define ACK_DELAY_MS 5
#define MAXPEND 64
static uint64_t ack_due[MAXPEND];
static int      n_ack_due;

typedef struct { uint64_t t_us; uint8_t b[20]; uint8_t n; uint8_t link; } wire_t;
static wire_t wire[4096];
static int    n_wire;
static uint8_t module_link = 0;          /* the slot the module is on (last select on the wire) */
static uint8_t host_state[6][8];         /* per-slot last keyboard state the host received */
static bool    host_got[6];

size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n) {
    (void)sd;
    if (n == 3 && b[0] == 0x61) return n; /* our own ACK token, not a frame */
    if (n_wire < 4096) {
        wire_t *w = &wire[n_wire++];
        w->t_us = now_us;
        w->n    = (uint8_t)(n > 20 ? 20 : n);
        memcpy(w->b, b, w->n);
        if (b[0] == 0xA6 && b[1] >= 0x30 && b[1] <= 0x35) module_link = b[1];
        w->link = module_link;
        if (b[0] == 0xA1 && module_link >= 0x30 && module_link <= 0x35) {
            memcpy(host_state[module_link - 0x30], b + 1, 8);
            host_got[module_link - 0x30] = true;
        }
    }
    if (acking && n_ack_due < MAXPEND) ack_due[n_ack_due++] = now_us + ACK_DELAY_MS * 1000;
    return n;
}
size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, sysinterval_t t) {
    (void)sd; (void)t;
    size_t k = 0;
    while (k < n && rx_r != rx_w) b[k++] = rxbuf[rx_r++ % RXCAP];
    return k;
}
static void rx_push(const uint8_t *b, size_t n) {
    for (size_t i = 0; i < n; i++) rxbuf[rx_w++ % RXCAP] = b[i];
}

/* ---- the rest of the board the daily driver links against ---- */
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void     watchdog_record_leave(uint32_t *saved) { (void)saved; }
bool     loop_acct_on = false;
uint32_t loop_acct_run[ACCT_N];
void     health_note_rx_malformed(void) {}
void     battery_5c_report(uint8_t pct) { (void)pct; }
void     send_raw_hid(uint8_t *data, uint8_t length) { (void)data; (void)length; }
bool     hid_rawhid_media_within(uint32_t now, uint32_t ms) { (void)now; (void)ms; return false; }
bool     hid_rawhid_clock_within(uint32_t s) { (void)s; return false; }

/* ---- driving ---- */
static int used(void) { return (int)((tx_tail - tx_head + CH582_TXQ_LEN) % CH582_TXQ_LEN); }

static void step_ms(int ms) {
    for (int i = 0; i < ms * 4; i++) {          /* main loop at 4 kHz */
        now_us += 250;
        for (int j = 0; j < n_ack_due;) {
            if (ack_due[j] <= now_us) {
                static const uint8_t ack[3] = {0x61, 0x0D, 0x0A};
                rx_push(ack, 3);
                ack_due[j] = ack_due[--n_ack_due];
            } else j++;
        }
        ch582_task();
    }
}
static void key(uint8_t kc) {
    report_keyboard_t r = {0};
    r.keys[0] = kc;
    bluetooth_send_keyboard(&r);
}
static void print_wire(int from) {
    for (int i = from; i < n_wire; i++) {
        printf("  [%8.1f ms] link %c  ", wire[i].t_us / 1000.0, wire[i].link ? wire[i].link : '-');
        for (int k = 0; k < wire[i].n; k++) printf("%02X ", wire[i].b[k]);
        printf("\n");
    }
}
static void reset_all(void) {
    /* fresh process per scenario is simpler: the driver's statics are file-scope */
}

static int scenario(bool near_full) {
    acking = true;
    bluetooth_init();
    ch582_set_profile(CH582_PROFILE_BT_1);
    step_ms(200);
    if (!module_alive) { printf("module never alive\n"); return 2; }
    /* The module announces the slot-1 link (5B 32, checksum 5B+32) and answers
     * the first battery poll (5C 50, checksum 5C+50), so the poll falls back
     * to its 5 s period and the queue below is filled by typing alone. */
    { static const uint8_t up[6] = {0x5B, 0x32, 0x8D, 0x5C, 0x50, 0xAC}; rx_push(up, 6); }
    step_ms(300);
    printf("  slot 1: conn_state %d connected %d battery_seen %d\n",
           (int)conn_state, (int)is_module_connected, (int)battery_seen);

    int stall_start = n_wire;
    acking = false;                   /* ACKs stall */
    uint8_t kc = 0x10;
    int     target = near_full ? 20 : 3;
    int     t_in_cycle = 0;
    bool    down = false;
    /* Type at ~100 wpm: a press every 120 ms, released 50 ms later. Stop
     * right after a release once the queue holds >= target frames. */
    for (int guard = 0; guard < 20000; guard++) {
        if (t_in_cycle == 0) { key(kc); down = true; }
        if (t_in_cycle == 50) { key(0); down = false; kc = (uint8_t)(kc == 0x27 ? 0x10 : kc + 1);
            if (used() >= target) break; }
        step_ms(1);
        t_in_cycle = (t_in_cycle + 1) % 120;
    }
    (void)down;
    printf("  after typing burst: queue used = %d, replaced so far = %lu, giveups = %lu\n",
           used(), (unsigned long)tx_stat_replaced, (unsigned long)tx_stat_giveup);
    printf("  last queued frame: ");
    { uint8_t li = (uint8_t)((tx_tail + CH582_TXQ_LEN - 1) % CH582_TXQ_LEN);
      for (int k = 0; k < tx_q[li].len; k++) printf("%02X ", tx_q[li].data[k]); printf("\n"); }

    /* Fn+W: bt_ui_slot_key -> select_slot -> ch582_set_profile(BT_2). Fn is a
     * layer key and the slot key returns false, so neither queues an A1. */
    ch582_set_profile(CH582_PROFILE_BT_2);
    printf("  Fn+W: queue used = %d\n", used());
    step_ms(getenv("A_DELAY_MS") ? atoi(getenv("A_DELAY_MS")) : 100);
    uint32_t rep0 = tx_stat_replaced;
    printf("  'a' pressed: queue used = %d\n", used());
    key(0x04);
    printf("  -> replaced %s (tx_stat_replaced %lu -> %lu)\n",
           tx_stat_replaced != rep0 ? "YES" : "no", (unsigned long)rep0, (unsigned long)tx_stat_replaced);
    acking = true;                    /* the module ACKs again */
    /* frames written while stalled are never ACKed; resend from the next */
    step_ms(3000);
    key(0);                           /* 'a' released after the drain */
    step_ms(500);

    int i_a = -1, i_sel = -1;
    for (int i = stall_start; i < n_wire; i++) {
        if (i_sel < 0 && wire[i].b[0] == 0xA6 && wire[i].b[1] == 0x32) i_sel = i;
        if (i_a < 0 && wire[i].b[0] == 0xA1 && wire[i].b[3] == 0x04) i_a = i;
    }
    printf("  wire around the select:\n");
    print_wire(i_sel - 4 > stall_start ? i_sel - 4 : stall_start);
    printf("  first 'A1 .. 04' at wire index %d (link %c), first 'A6 32' at %d\n",
           i_a, i_a >= 0 ? wire[i_a].link : '?', i_sel);
    printf("  host on slot 1 left with keys: %02X %02X %02X ... ; slot 2 got any A1: %s\n",
           host_state[1][2], host_state[1][3], host_state[1][4], host_got[2] ? "yes" : "no");
    bool slot2_saw_a = false;
    for (int i = stall_start; i < n_wire; i++)
        if (wire[i].link == 0x32 && wire[i].b[0] == 0xA1 && wire[i].b[3] == 0x04) slot2_saw_a = true;
    printf("  slot 2 ever received the 'a' press: %s\n", slot2_saw_a ? "yes" : "NO");
    bool bug = (i_a >= 0 && i_sel >= 0 && i_a < i_sel);
    printf("  RESULT: %s\n", bug ? "BUG -- the key pressed after the select went out before it, on slot 1's link"
                                 : "ok -- the key went out after the select");
    return bug ? 1 : 0;
}

int main(int argc, char **argv) {
    bool near_full = !(argc > 1 && strcmp(argv[1], "control") == 0);
    printf("== scenario %s\n", near_full ? "A: select with >= 20 frames queued (the finding's trigger)"
                                         : "B (control): select with the queue nearly empty");
    reset_all();
    return scenario(near_full);
}
