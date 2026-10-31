/* A host LED frame (5A) that reaches UART2's input queue after the pass's
 * radio drain and before deep_sleep()'s lock holds the sleep off, so the next
 * pass takes it (plans/AUDIT-2026-10-31.md, F-020; first written as the
 * audit's verify-032). Before the fix the admission passed and the wake's
 * iqResetI() threw the frames away, leaving host_leds stale.
 *
 * Built from the real, unedited firmware files by path:
 *   keyboards/a_jazz/ak820pro/sleep.c              (sleep_task, deep_sleep)
 *   keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c  (ch582_task, the parser, host_leds)
 * The daily build's configuration (no AK820_DEV_HOOKS), as releases ship.
 * The UART2 RX ISR is modelled by its body's one queue operation,
 * iqPutI(&SD2.iqueue, RB) (hal_serial_lld.c:320), called only outside the lock.
 * One main-loop pass is modelled as: ch582_task() (bluetooth_task, inside
 * keyboard_task), then the rest of the pass, then sleep_task() (ak820pro.c:678). */
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include "stubs/fw_hal_stub.h"
#include "sleep.h"
#include "bluetooth/ch582f_ajazz.h"

void bluetooth_init(void);

extern uint32_t g_ms;
extern bool     g_sleep_wanted;
extern size_t   g_iq_reset_discarded;
extern unsigned g_iq_resets;
extern unsigned g_pending_module_acks;
extern void (*g_during_pcf_read)(void);

static int fails;
#define CHECK(c, ...) do { if (c) { printf("ok   " __VA_ARGS__); printf("\n"); } \
                           else { printf("FAIL " __VA_ARGS__); printf("   [%s:%d %s]\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* The UART2 RX ISR's body for each byte (outside the lock only). */
static void isr_rx(const uint8_t *b, size_t n) {
    assert(g_lock_depth == 0);
    for (size_t i = 0; i < n; i++) (void)iqPutI(&SD2.iqueue, b[i]);
}

/* The module: every command frame the board sent is ACKed (61 0D 0A) by the
 * next pass, so the board's TX side goes quiet as it does on a live link. */
static void module_acks(void) {
    static const uint8_t ack[3] = {0x61, 0x0D, 0x0A};
    while (g_pending_module_acks) {
        g_pending_module_acks--;
        isr_rx(ack, 3);
    }
}

static unsigned wfi_calls;
void ds_wfi_hook(void) {
    /* Asleep. The host's frames now would be lost by design (RXEN is off);
     * none are sent here. A key press ends the sleep: column A4 (P0 bit 4). */
    wfi_calls++;
    g_gpio0.RIS |= 1u << 4;
}

/* One main-loop pass. `window` runs between the radio drain and sleep_task:
 * QMK's remaining keyboard_task, the pump, the 10 Hz block, flash_tidy. */
static void pass(void (*window)(void)) {
    module_acks();
    ch582_task();
    if (window) window();
    g_ms += 1;
    sleep_task();
}

static void idle_passes(unsigned ms) {
    for (unsigned i = 0; i < ms; i++) pass(NULL);
}

/* What the host does: Caps goes off. The module forwards every change three
 * times, 0-5 ms apart (docs/wireless.md, "Every change arrives three times"). */
static const uint8_t CAPS_OFF_X3[9] = {0x5A, 0x00, 0x5A, 0x5A, 0x00, 0x5A, 0x5A, 0x00, 0x5A};
static void host_caps_off(void) { isr_rx(CAPS_OFF_X3, sizeof CAPS_OFF_X3); }

static void board_to_idle_caps_on(void) {
    static bool booted;
    if (!booted) {
        bluetooth_init();
        booted = true;
        static const uint8_t link_up[3] = {0x5B, 0x32, 0x8D};   /* 5B 32: connected */
        isr_rx(link_up, 3);
        idle_passes(5);
    }
    static const uint8_t caps_on[3] = {0x5A, 0x02, 0x5C};      /* 5A 02: Caps on */
    isr_rx(caps_on, 3);
    idle_passes(5);
    assert(ch582_get_host_leds() == 0x02);
    /* Let any recovery from an earlier sleep end (its USB step takes 3 s),
     * the battery poll go and be ACKed, and USB read as absent (100 ms). */
    idle_passes(4000);
    /* Stand just after a battery poll was ACKed, so no TX is due in the
     * sleeping pass (polls every 5 s). */
    while (!ch582_tx_idle() || g_pending_module_acks) pass(NULL);
}

int main(void) {
    /* Registers as an idle board on battery reads them. */
    g_uart2.LS   = 1u << 6;            /* TEMT; RDR clear: the 1-byte receiver holds nothing */
    g_wdt.CFG    = 1u;                 /* WDTEN */
    g_sys0.CSST  = 0x41u;              /* IHRCRDY, PLLRDY */
    g_gpio0.DATA = g_gpio1.DATA = g_gpio2.DATA = 0xFFFFFFFFu;   /* columns and CHRG high */

    /* ---- Control: the frame lands BEFORE the sleeping pass's drain ---- */
    board_to_idle_caps_on();
    printf("host_leds before control = 0x%02x (Caps on)\n", ch582_get_host_leds());
    host_caps_off();
    g_sleep_wanted = true;
    unsigned w0 = wfi_calls, r0 = g_iq_resets;
    pass(NULL);
    g_sleep_wanted = false;
    g_gpio0.RIS = 0;
    CHECK(wfi_calls > w0, "control: the board deep-slept in that pass");
    CHECK(g_iq_resets == r0 + 1 && g_iq_reset_discarded == 0, "control: the wake's iqResetI found the queue empty (discarded %zu)", g_iq_reset_discarded);
    CHECK(ch582_get_host_leds() == 0x00, "control: host_leds follows the host (0x%02x, want 0x00)", ch582_get_host_leds());

    /* ---- The finding: the frame lands AFTER the drain, before the lock ---- */
    board_to_idle_caps_on();
    printf("host_leds before trigger = 0x%02x (Caps on)\n", ch582_get_host_leds());
    g_during_pcf_read = host_caps_off;   /* during rtc_sleep_prepare()'s PCF read */
    g_sleep_wanted    = true;
    w0 = wfi_calls; r0 = g_iq_resets;
    pass(NULL);                          /* drain (empty), then sleep_task */
    g_sleep_wanted    = false;
    g_during_pcf_read = NULL;
    g_gpio0.RIS = 0;
    CHECK(wfi_calls == w0, "trigger: the admission refused the sleep with bytes queued");
    CHECK(g_iq_resets == r0, "trigger: no wake, no iqResetI");
    idle_passes(50);                     /* the passes after the wake drain an empty queue */
    CHECK(ch582_get_host_leds() == 0x00,
          "trigger: host_leds follows the host after the wake (0x%02x, want 0x00: Caps off)", ch582_get_host_leds());
    idle_passes(10000);                  /* nothing re-sends it: the module forwards changes only */
    CHECK(ch582_get_host_leds() == 0x00, "trigger: still the host's 10 s later (0x%02x)", ch582_get_host_leds());
    /* And the sleep the frames held off comes: the queue drained, a pass tries again. */
    g_sleep_wanted = true;
    w0 = wfi_calls;
    pass(NULL);
    pass(NULL);
    g_sleep_wanted = false;
    g_gpio0.RIS = 0;
    CHECK(wfi_calls > w0, "trigger: the sleep follows once the queue is drained");

    printf("RESULT: %s\n", fails ? "FAIL" : "PASS");
    return fails ? 1 : 0;
}
