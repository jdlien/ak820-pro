/* The raw-HID receive and reply loop under backpressure (codex's review of the
 * 10-31 audit's Batch 4, P1 on F-001). tmk_core's send_raw_hid() and
 * raw_hid_task(), extracted verbatim from usb_main.c by run.sh, against a model
 * of usb_endpoint_in_send() (usb_driver.c): RAW_IN_CAPACITY buffers; a send
 * into a full queue waits for the host to take one, up to its 100 ms timeout,
 * after which the queue is reset and the endpoint's timed_out latch makes the
 * next waits immediate until a transfer completes.
 *
 * The host: it keeps the OUT queue full (a report is always waiting) and takes
 * one IN report every 50 ms, so no send ever times out. The board's handler
 * answers every report, as the flash channel's FS_BUSY does. The main loop runs
 * raw_hid_task() and then housekeeping, where the watchdog is fed (~12 s).
 *
 * Built twice: with the board's RAW_HID_TASK_MAX_REPORTS (config.h) the gap
 * between housekeeping passes must stay under a second; without it, the
 * control, the model must show the watchdog starving, or the test proves
 * nothing. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAW_EPSIZE 32
#define RAW_IN_CAPACITY 4
typedef enum { USB_ENDPOINT_IN_RAW } usb_endpoint_in_lut_t;
typedef enum { USB_ENDPOINT_OUT_RAW } usb_endpoint_out_lut_t;

#define WDT_MS 12000.0
#define TAKE_MS 50.0      /* the host takes one IN report this often */
#define TIMEOUT_MS 100.0  /* send_report()'s TIME_MS2I(100) */
#define HANDLER_MS 0.05   /* the handler's own work, a busy reply's */

static double   now_ms;
static double   next_take_ms = TAKE_MS;
static unsigned in_queued;     /* IN buffers holding a report */
static bool     timed_out;
static double   pass_start_ms;
static bool     wdt_starved;
static unsigned received, sent, timeouts;

/* The host's side of the IN endpoint, caught up to `now_ms`. */
static void host_takes(void) {
    while (next_take_ms <= now_ms) {
        if (in_queued) {
            in_queued--;
            timed_out = false;   /* usb_driver.c:198, a transfer completed */
        }
        next_take_ms += TAKE_MS;
    }
}

static bool send_report(usb_endpoint_in_lut_t ep, void *report, size_t size) {
    (void)ep; (void)report; (void)size;
    host_takes();
    double timeout = timed_out ? 0.0 : TIMEOUT_MS;
    for (;;) {
        if (in_queued < RAW_IN_CAPACITY) {
            in_queued++;
            sent++;
            return true;
        }
        if (next_take_ms - now_ms <= timeout) {   /* obqWriteTimeout waits for a free buffer */
            now_ms = next_take_ms;
            host_takes();
            continue;
        }
        now_ms += timeout;                        /* sent == 0: the latch, the queue reset, retried */
        timeouts++;
        timed_out = true;
        in_queued = 0;
        timeout   = 0.0;
        host_takes();
    }
}

/* The host keeps a report waiting. The model stops the drain only once the
 * watchdog would have fired, so the uncapped control ends. */
static bool receive_report(usb_endpoint_out_lut_t ep, void *report, size_t size) {
    (void)ep;
    if (now_ms - pass_start_ms > WDT_MS) {
        wdt_starved = true;
        return false;
    }
    memset(report, 0, size);
    received++;
    return true;
}

static void send_raw_hid(uint8_t *data, uint8_t length);
static void raw_hid_receive(uint8_t *data, uint8_t length) {
    now_ms += HANDLER_MS;
    send_raw_hid(data, length);   /* FS_BUSY, or any reply */
}

#include "raw.inc"

int main(void) {
    double   last_hk = 0.0, worst_gap = 0.0;
    unsigned passes  = 0;
    while (now_ms < 30000.0 && !wdt_starved) {
        pass_start_ms = now_ms;
        raw_hid_task();
        now_ms += 2.9;   /* the rest of a ~335 Hz pass */
        double gap = now_ms - last_hk;
        if (gap > worst_gap) worst_gap = gap;
        last_hk = now_ms;   /* housekeeping: the watchdog fed */
        passes++;
    }
    printf("  %.0f ms simulated, %u passes, %u reports handled, %u replies, %u timeouts, worst gap %.1f ms%s\n",
           now_ms, passes, received, sent, timeouts, worst_gap, wdt_starved ? ", the WATCHDOG STARVED" : "");
#ifdef RAW_HID_TASK_MAX_REPORTS
    int ok = !wdt_starved && worst_gap < 1000.0 && received > 500;
    printf("%s: capped at %d a pass, the main loop keeps reaching housekeeping\n", ok ? "PASS" : "FAIL",
           RAW_HID_TASK_MAX_REPORTS);
#else
    int ok = wdt_starved;
    printf("%s: uncapped (the control), the model starves the watchdog\n", ok ? "PASS" : "FAIL");
#endif
    return ok ? 0 : 1;
}
