/* The radio side of the host world: the UART that ch582f_ajazz.c talks to,
 * and a model of the CH582F module behind it. Compiled against stubs_radio/
 * (the same stubs the radio-link reproducer used).
 *
 * The module model follows what the repo records about the wire:
 *   - every checksummed frame we send is ACKed with 61 0D 0A (docs/wireless.md);
 *   - A6 53 (battery poll) is answered with a 5C frame;
 *   - A6 <slot> starts an attempt: 5B 33, then 5B 32 when the slot's host is
 *     there (the select/attempt traces in ch582f_ajazz.c's comments);
 *   - A6 51 while attempting is dropped (wireless.md, "A6 51 is ignored while
 *     a connect attempt is in flight"); otherwise it starts advertising: 5B 31;
 *   - while advertising the module is silent to A6 <same slot> and A6 51
 *     (wireless.md: "It emits nothing at all while advertising");
 *   - the advertising window lasts minutes and ends with 5B 23
 *     (wireless.md: "The advertising window lasts minutes"; the trace at
 *     ch582f_ajazz.c:110-114; CONFIG-MENU-P1-DESIGN.md's "Known gap");
 *   - 5B 23 also comes periodically in any state (ch582f_ajazz.c:2168).
 * What the module does AFTER advertising ends unpaired is the one thing not
 * captured anywhere in the repo; mod_reconnect_after_adv picks it. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hal.h"
#include "quantum.h"
#undef printf   /* stubs_radio/quantum.h silences the driver's printf; the model talks */

extern uint32_t now_ms;

/* SD2 is defined in world_sys.c (the larger stub view of the type). */
bool loop_acct_on = false;

/* bytes waiting in the UART for the driver */
static uint8_t rxq[8192];
static size_t  rx_h = 0, rx_t = 0;
static void rx_push(const uint8_t *b, size_t n) {
    for (size_t i = 0; i < n; i++) { rxq[rx_t] = b[i]; rx_t = (rx_t + 1) % sizeof rxq; }
}

/* ---- the module model ---- */
enum { M_IDLE, M_ATTEMPT, M_CONNECTED, M_ADVERTISING };
static const char *mstate_name[] __attribute__((unused)) = {"idle", "attempting", "connected", "advertising"};
int      mod_state              = M_IDLE;
uint8_t  mod_slot               = 0;
uint32_t mod_adv_end            = 0;
uint32_t mod_adv_ms             = 180000;  /* "minutes" */
uint32_t mod_23_period_ms       = 60000;   /* periodic 5B 23 */
bool     mod_reconnect_after_adv = false;  /* hypothetical: reconnect the old host when advertising ends */
bool     mod_drop_next_5b31     = false;   /* a 5B 31 lost on the wire (UART overrun) */
uint32_t mod_frames_5b[256];               /* 5B codes delivered, by code */
static uint32_t last_23 = 0;

typedef struct { uint32_t at; uint8_t b[3]; uint8_t n; int new_state; } ev_t;
static ev_t evq[512];
static int  evn = 0;

static void sched(uint32_t delay, const uint8_t *b, uint8_t n, int new_state) {
    if (evn >= (int)(sizeof evq / sizeof evq[0])) { fprintf(stderr, "event queue full\n"); exit(2); }
    ev_t *e = &evq[evn++];
    e->at = now_ms + delay; memcpy(e->b, b, n); e->n = n; e->new_state = new_state;
}
static void sched5(uint32_t delay, uint8_t t, uint8_t d, int new_state) {
    uint8_t f[3] = {t, d, (uint8_t)(t + d)};
    sched(delay, f, 3, new_state);
}

static int verbose_mod = 0;
void module_verbose(int v) { verbose_mod = v; }

/* Called once per simulated ms, before the driver's pass. */
void module_tick(void) {
    /* deliver due events, in schedule order */
    for (int i = 0; i < evn;) {
        if ((int32_t)(now_ms - evq[i].at) >= 0) {
            ev_t e = evq[i];
            memmove(&evq[i], &evq[i + 1], (size_t)(evn - i - 1) * sizeof(ev_t));
            evn--;
            if (e.new_state >= 0) mod_state = e.new_state;
            if (e.n == 3 && e.b[0] == 0x5B) {
                mod_frames_5b[e.b[1]]++;
                if (e.b[1] == 0x31 && mod_drop_next_5b31) {
                    mod_drop_next_5b31 = false;
                    if (verbose_mod) printf("  [%8.3f s] module: 5B 31 LOST on the wire\n", now_ms / 1000.0);
                    continue;
                }
                if (verbose_mod && e.b[1] != 0x23)
                    printf("  [%8.3f s] module -> 5B %02X (module %s)\n", now_ms / 1000.0, e.b[1], mstate_name[mod_state]);
            }
            rx_push(e.b, e.n);
        } else {
            i++;
        }
    }
    /* the advertising window ends */
    if (mod_state == M_ADVERTISING && (int32_t)(now_ms - mod_adv_end) >= 0) {
        mod_state = M_IDLE;
        if (verbose_mod) printf("  [%8.3f s] module: advertising window over, nobody paired -> 5B 23\n", now_ms / 1000.0);
        sched5(0, 0x5B, 0x23, -1);
        last_23 = now_ms;
        if (mod_reconnect_after_adv) {
            sched5(50, 0x5B, 0x33, M_ATTEMPT);
            sched5(500, 0x5B, 0x32, M_CONNECTED);
        }
    }
    /* the periodic 5B 23 (ignored by the driver in every state) */
    if (mod_state != M_ADVERTISING && now_ms - last_23 >= mod_23_period_ms) {
        last_23 = now_ms;
        sched5(0, 0x5B, 0x23, -1);
    }
}

static void module_rx(const uint8_t *b, size_t n) {
    if (n == 3 && b[0] == 0x61 && b[1] == 0x0D && b[2] == 0x0A) return;   /* the driver's own ACK */
    if (n != 3 || b[0] != 0xA6 || (uint8_t)(b[0] + b[1]) != b[2]) return;
    static const uint8_t ack[3] = {0x61, 0x0D, 0x0A};
    sched(1, ack, 3, -1);
    uint8_t p = b[1];
    if (p == 0x53) {                                    /* battery poll */
        sched5(3, 0x5C, 80, -1);
    } else if (p >= 0x31 && p <= 0x33) {                /* select a BT slot */
        if (verbose_mod) printf("  [%8.3f s] module <- A6 %02X (select slot %d)\n", now_ms / 1000.0, p, p - 0x30);
        if (mod_state == M_ADVERTISING && p == mod_slot) return;   /* silent: same slot while advertising */
        mod_slot  = p;
        mod_state = M_ATTEMPT;
        sched5(50, 0x5B, 0x33, M_ATTEMPT);
        sched5(500, 0x5B, 0x32, M_CONNECTED);           /* the slot's host is there */
    } else if (p == 0x51) {                             /* pair */
        if (verbose_mod) printf("  [%8.3f s] module <- A6 51 (pair) while %s\n", now_ms / 1000.0, mstate_name[mod_state]);
        if (mod_state == M_ATTEMPT || mod_state == M_ADVERTISING) return;   /* dropped / silent */
        mod_state   = M_ADVERTISING;
        mod_adv_end = now_ms + mod_adv_ms;
        sched5(80, 0x5B, 0x31, -1);
    }
}

/* ---- the UART the driver sees ---- */
void sdStart(SerialDriver *sdp, const SerialConfig *cfg) { (void)sdp; (void)cfg; }
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t) {
    (void)sdp; (void)t;
    size_t k = 0;
    while (k < n && rx_h != rx_t) { b[k++] = rxq[rx_h]; rx_h = (rx_h + 1) % sizeof rxq; }
    return k;
}
size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n) {
    (void)sdp;
    module_rx(b, n);
    return n;
}
void chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f) {
    (void)es; (void)el; (void)m; (void)f;
}
eventflags_t chEvtGetAndClearFlags(event_listener_t *el) { (void)el; return 0; }
void battery_5c_report(uint8_t d) { (void)d; }
void health_note_rx_malformed(void) {}
