/* usb_wakeup_try(), the board's only remote wake (plans/AUDIT-2026-10-31.md,
 * F-007 and F-028; first written as the audit's verify-028 and verify-034).
 * The function is ak820pro.c's own text, extracted by run.sh; timer_elapsed32()
 * is the real platforms/timer.c, and timer_read32() a millisecond counter the
 * test drives. */
#include <stdio.h>
#include "stubs.h"

USBDriver USBD1;
static uint32_t now_ms;
static unsigned wake_calls;
static connection_host_t host = CONNECTION_HOST_USB;

uint32_t timer_read32(void) { return now_ms; }
uint16_t timer_read(void)   { return (uint16_t)timer_read32(); }  /* chibios/timer.c */
connection_host_t connection_get_host(void) { return host; }
void usbWakeupHost(USBDriver *usbp) { if (usbp->state == USB_SUSPENDED) wake_calls++; }

#include "x_wakeup.inc"

static int fails;
static void check(bool ok, const char *what) {
    printf("%s: %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) fails++;
}
/* The host suspended with remote wakeup armed (SET_FEATURE sets status bit
 * 1), then a press at t, routed to h. True if the press sent the K-state. */
static bool press(uint32_t t, connection_host_t h, usbstate_t st, uint16_t status) {
    USBD1.state = st;
    USBD1.status = status;
    host = h;
    now_ms = t;
    unsigned before = wake_calls;
    usb_wakeup_try();
    return wake_calls > before;
}
static bool press_usb(uint32_t t) { return press(t, CONNECTION_HOST_USB, USB_SUSPENDED, 2); }

int main(void) {
    (void)battery_usb_configured;
    uint32_t t = 1000000u;

    /* F-007: a key that goes to the radio never wakes the computer on the cable. */
    check(!press(t, CONNECTION_HOST_BLUETOOTH, USB_SUSPENDED, 2), "slider on BT: no wake of the USB host");
    check(!press(t, CONNECTION_HOST_2P4GHZ, USB_SUSPENDED, 2), "slider on 2.4G: no wake of the USB host");
    unsigned radio = 0;
    for (uint32_t i = 0; i < 7200; i++) radio += press(t + 250u * i, CONNECTION_HOST_BLUETOOTH, USB_SUSPENDED, 2);
    check(radio == 0, "30 min of typing over BT: the USB host never woken");
    check(!press(t, CONNECTION_HOST_USB, USB_ACTIVE, 2), "USB host awake: no wake");
    check(!press(t, CONNECTION_HOST_USB, USB_SUSPENDED, 0), "USB host suspended without remote wake armed: no wake");
    check(press_usb(t), "slider on cable, host suspended and armed: the press wakes it");
    check(!press_usb(t + 300u), "a second press 300 ms later: inside the 500 ms rate limit");
    check(press_usb(t + 500u), "a press 500 ms after the try: sent");
    t += 500u;

    /* F-028: a 16-bit stamp read a press within 500 ms of each 65.536 s after
     * the last try as "just tried". 9 h on, 120 ms past an alias: */
    uint32_t gap = 495u * 65536u + 120u;
    check(press_usb(t + gap), "a press 9 h after the last try, 120 ms past a 65.536 s alias: sent");
    t += gap;
    /* Every gap from 0.5 s to 4 x 65.536 s in 7 ms steps: all >= 500 ms, so
     * none may be skipped. */
    unsigned n = 0, skipped = 0;
    for (uint32_t d = 500u; d < 500u + 4u * 65536u; d += 7u) {
        n++;
        if (press_usb(t + d)) { t += d; continue; }
        skipped++;
        t += d;
    }
    printf("      sweep: %u of %u first presses skipped\n", skipped, n);
    check(skipped == 0, "no first press skipped at any gap of 500 ms or more");

    printf(fails ? "RESULT: FAIL (%d)\n" : "RESULT: PASS\n", fails);
    return fails ? 1 : 0;
}
