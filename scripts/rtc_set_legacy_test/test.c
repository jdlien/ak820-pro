/* The legacy RTC_SET_TIME's validation (plans/AUDIT-2026-10-31.md, F-016;
 * first found by the audit's verify-007, the clock reviewer and two fuzzers).
 * rtc_apply_bytes() is hid_protocol.c's own text, extracted by run.sh, with
 * rtc/rtc_payload.h's real month table; rtc_set_time() and the owner stamp
 * are stubs that record a call. Every year, month and day byte is tried: a
 * date reaches the battery-backed PCF only if it exists and its year is
 * 2000..2098. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

typedef struct { uint16_t year; uint8_t month, day, weekday, hours, minutes, seconds; } rtc_time_t;
#include "rtc_payload_month.inc"

static int sets;
static bool rtc_set_time(const rtc_time_t *t) { (void)t; sets++; return true; }
static void rawhid_clock_set(void) {}

#include "x_apply.inc"

static bool real_date(int yy, int mo, int dd) {
    if (yy > 98 || mo < 1 || mo > 12 || dd < 1) return false;
    struct tm tm = { .tm_year = 100 + yy, .tm_mon = mo - 1, .tm_mday = dd, .tm_hour = 12 };
    time_t t = timegm(&tm);
    struct tm back;
    gmtime_r(&t, &back);
    return back.tm_mday == dd && back.tm_mon == mo - 1;   /* timegm() normalizes an impossible one */
}

int main(void) {
    int wrong = 0, accepted = 0;
    for (int yy = 0; yy < 256; yy++)
        for (int mo = 0; mo < 256; mo++)
            for (int dd = 0; dd < 64; dd++) {
                uint8_t p[7] = { (uint8_t)yy, (uint8_t)mo, (uint8_t)dd, 3, 12, 0, 0 };
                int before = sets;
                rtc_apply_bytes(p);
                bool took = sets != before, want = real_date(yy, mo, dd);
                accepted += took;
                if (took != want) {
                    if (wrong < 10) printf("FAIL: %02u-%02u-%02u %s\n", yy, mo, dd, took ? "accepted" : "refused");
                    wrong++;
                }
            }
    uint8_t leap[7] = { 28, 2, 29, 2, 12, 0, 0 }, noleap[7] = { 26, 2, 29, 2, 12, 0, 0 };
    int s0 = sets;
    rtc_apply_bytes(leap);
    bool leap_ok = sets == s0 + 1;
    rtc_apply_bytes(noleap);
    bool noleap_refused = sets == s0 + 1;
    printf("%d dates accepted, %d wrong; 2028-02-29 %s, 2026-02-29 %s\n", accepted, wrong,
           leap_ok ? "accepted" : "REFUSED", noleap_refused ? "refused" : "ACCEPTED");
    bool pass = !wrong && leap_ok && noleap_refused;
    printf("RESULT: %s\n", pass ? "PASS" : "FAIL");
    return pass ? 0 : 1;
}
