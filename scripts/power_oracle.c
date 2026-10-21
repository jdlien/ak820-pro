/* The power page's oracle (scripts/power_model.py --oracle): the firmware's own
 * colour and model code, at the commit deps.lock pins, run on the host, so
 * site/power/model.test.js can hold model.js to it exactly.
 *
 * Built against the pinned quantum/color.c and led_tables.c (USE_CIE1931_CURVE,
 * as common_features.mk sets it for RGB matrix boards), and battery.c's
 * model_nj with its #defines, copied verbatim into model_extract.h by the
 * generator. Its two inputs, the backlight's duty and USB, are stubs here.
 *
 *   oracle hsv     every h and v for ten saturations, r g b bytes to stdout
 *   oracle model   lines of "dt r_ms g_ms b_ms lit_ms duty usb" on stdin,
 *                  model_nj's nJ for each to stdout
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "color.h"

static uint8_t duty_now;
static bool    usb_now;
static uint8_t display_backlight_duty(void) { return duty_now; }
static bool    battery_usb_configured(void) { return usb_now; }

#include "model_extract.h"

static const uint8_t SATS[] = {0, 1, 2, 64, 127, 128, 129, 200, 254, 255};   /* model.test.js's list */

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "hsv") == 0) {
        for (unsigned i = 0; i < sizeof(SATS); i++)
            for (unsigned h = 0; h < 256; h++)
                for (unsigned v = 0; v < 256; v++) {
                    hsv_t in  = {.h = (uint8_t)h, .s = SATS[i], .v = (uint8_t)v};
                    rgb_t out = hsv_to_rgb(in);
                    uint8_t b[3] = {out.r, out.g, out.b};
                    fwrite(b, 1, 3, stdout);
                }
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "model") == 0) {
        unsigned long dt, lit, duty, usb;
        unsigned long long r, g, b;
        while (scanf("%lu %llu %llu %llu %lu %lu %lu", &dt, &r, &g, &b, &lit, &duty, &usb) == 7) {
            uint64_t rgb_ms[3] = {r, g, b};
            duty_now = (uint8_t)duty;
            usb_now  = usb != 0;
            printf("%llu\n", (unsigned long long)model_nj((uint32_t)dt, rgb_ms, (uint32_t)lit));
        }
        return 0;
    }
    fprintf(stderr, "usage: oracle hsv | oracle model < cases\n");
    return 2;
}
