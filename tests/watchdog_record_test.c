/* Host simulation of warm resets using the actual portable firmware recorder.
 * cc -std=c11 -Wall -Wextra -Werror tests/watchdog_record_test.c -o /tmp/wdt-test
 * /tmp/wdt-test
 */
#define WATCHDOG_RECORD_TEST
#include "../qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/watchdog_record.c"
#include <assert.h>
#include <stdio.h>

static uint8_t record[28];
static void boot(uint8_t flags) {
    ready = false; /* crt0 clears BSS; ram7 remains */
    memset(boot_record, 0, sizeof(boot_record));
    watchdog_record_boot(flags);
    watchdog_record_fill(record);
}
static void early_return(void) {
    WDT_SCOPE(WDT_SITE_I2C_READ);
    assert((uint8_t)retained.path == WDT_SITE_I2C_READ);
    return;
}
int main(void) {
    /* A power-on, an old-layout image and random RAM never fabricate evidence. */
    boot(16);
    assert(!record[1] && record[9] == 0);
    retained.magic = 0x4A445721u;
    retained.path = encode_path(WDT_SITE_LCD_WAIT);
    boot(2);
    assert(!record[1] && record[9] == 1);
    boot(16);

    /* Before boot capture even marked init paths cannot destroy evidence. */
    watchdog_record_uptime(0x12345678u);
    watchdog_record_enter(WDT_SITE_DISPLAY_PUMP);
    watchdog_record_enter(WDT_SITE_LCD_WAIT);
    uint32_t interrupted = retained.path;
    ready = false;
    uint32_t inert = watchdog_record_enter(WDT_SITE_FLASH_READ);
    watchdog_record_leave(&inert);
    assert(retained.path == interrupted);
    boot(2);
    assert(record[1] && record[2] == WDT_SITE_LCD_WAIT && record[3] == WDT_SITE_DISPLAY_PUMP);
    assert(record[4] == 0x78 && record[5] == 0x56 && record[6] == 0x34 && record[7] == 0x12);
    assert(record[8] == 2 && record[9] == 1);
    for (int i = 10; i < 28; ++i) assert(record[i] == 0);

    /* Live work never changes the frozen report, even after early returns. */
    uint8_t saved[28]; memcpy(saved, record, 28);
    early_return();
    assert((uint8_t)retained.path == WDT_SITE_MAIN_LOOP);
    {
        WDT_SCOPE(WDT_SITE_HOUSEKEEPING);
        early_return();
        assert((uint8_t)retained.path == WDT_SITE_HOUSEKEEPING);
    }
    assert((uint8_t)retained.path == WDT_SITE_MAIN_LOOP);
    watchdog_record_uptime(999);
    watchdog_record_fill(record);
    assert(memcmp(saved, record, 28) == 0);

    /* Consecutive resets still reach degraded mode; count saturates. */
    boot(2); assert(record[9] == 2);
    boot(2); assert(record[9] == 3);
    retained.count = 255; boot(2); assert(record[9] == 255);
    boot(1); assert(!record[1] && record[9] == 0);
    retained.path ^= 1u << 16; boot(2); assert(!record[1]);
    for (int i = 2; i < 8; ++i) assert(record[i] == 0);
    watchdog_record_enter(WDT_SITE_LCD_WAIT);
    boot(2 | 4); assert(!record[1] && record[9] == 1);
    watchdog_record_enter(WDT_SITE_LCD_WAIT);
    boot(2 | 16); assert(!record[1] && record[9] == 1);
    /* ---- terminal records (crash-hunt plan B1) ---- */
    static uint32_t ram[64];   /* stands in for SRAM: the frame bounds */
    test_frame_lo = (uintptr_t)ram;
    test_frame_hi = (uintptr_t)(ram + 64);
    uint32_t *frame = &ram[8];
    frame[6] = 0x0001A2B4u;            /* stacked PC */
    frame[7] = 0x01000000u | 20u;      /* xPSR: Thumb, inside IRQ 4 */

    /* A fault inside an operation: site hard_fault, parent the operation,
     * PC and exception in format 2, no uptime. */
    boot(1);
    {
        WDT_SCOPE(WDT_SITE_DISPLAY_PUMP);
        {
            WDT_SCOPE(WDT_SITE_LCD_WAIT);
            watchdog_record_uptime(4242);
            watchdog_record_fault_frame((uintptr_t)frame);
            /* The first terminal record wins; nothing overwrites it. */
            watchdog_record_stop(WDT_SITE_HALT, 0, 0x1234);
            assert(retained.magic == FAULT_MAGIC);
        }
    }
    boot(2);
    assert(record[0] == 2 && record[1] == 1);
    assert(record[2] == WDT_SITE_HARD_FAULT && record[3] == WDT_SITE_LCD_WAIT);
    for (int i = 4; i < 8; ++i) assert(record[i] == 0);          /* no uptime */
    assert(record[8] == 2 && record[9] == 1);
    assert(record[10] == 0xB4 && record[11] == 0xA2 && record[12] == 0x01 && record[13] == 0);
    assert(record[14] == 20);
    for (int i = 15; i < 28; ++i) assert(record[i] == 0);
    assert(retained.magic == RECORD_MAGIC && retained.count == 1);  /* back to normal */

    /* Thread context reads exception 0. */
    frame[7] = 0x01000000u;
    watchdog_record_fault_frame((uintptr_t)frame);
    boot(2);
    assert(record[0] == 2 && record[14] == 0 && record[9] == 2);
    assert(record[3] == WDT_SITE_MAIN_LOOP);

    /* An unreadable frame is never loaded from: misaligned, below SRAM, or
     * running past its end. PC 0xFFFFFFFF, exception unknown. */
    uintptr_t bad[] = { (uintptr_t)frame + 2, test_frame_lo - 32, test_frame_hi - 28, 0 };
    for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        boot(1);
        watchdog_record_fault_frame(bad[i]);
        boot(2);
        assert(record[0] == 2 && record[1] == 1 && record[2] == WDT_SITE_HARD_FAULT);
        for (int j = 10; j < 14; ++j) assert(record[j] == 0xFF);
        assert(record[14] == 0xFF);
    }
    /* The last word of SRAM is a valid frame end. */
    boot(1);
    watchdog_record_fault_frame(test_frame_hi - 32);
    boot(2);
    assert(record[0] == 2 && record[14] != 0xFF);

    /* Other terminal sites carry what they know. */
    boot(1);
    watchdog_record_stop(WDT_SITE_UNHANDLED_EXCEPTION, 19, 0);
    boot(2);
    assert(record[0] == 2 && record[2] == WDT_SITE_UNHANDLED_EXCEPTION && record[14] == 19);
    for (int i = 10; i < 14; ++i) assert(record[i] == 0);

    /* Before boot capture a terminal write must not destroy the previous
     * boot's unread evidence. */
    boot(1);
    watchdog_record_enter(WDT_SITE_I2C_WRITE);
    ready = false;
    watchdog_record_fault_frame((uintptr_t)frame);
    assert(retained.magic == RECORD_MAGIC);
    boot(2);
    assert(record[0] == 1 && record[2] == WDT_SITE_I2C_WRITE);

    /* A reset part-way through the commit leaves no magic, so no record --
     * never a PC under the ordinary magic. */
    boot(1);
    retained.magic = 0;
    retained.count = 1u | (20u << 8);
    retained.pass_uptime_ms = 0x0001A2B4u;
    boot(2);
    assert(record[0] == 1 && !record[1] && record[9] == 1);

    /* A terminal record's count word validates as packed; junk above the
     * exception byte is corruption, not a count. */
    boot(1);
    watchdog_record_stop(WDT_SITE_HALT, 0, 0x2000);
    retained.count |= 1u << 16;
    boot(2);
    assert(!record[1] && record[9] == 1);
    /* ...and an ordinary count above 255 is corruption too. */
    retained.count = 256;
    boot(2);
    assert(!record[1] && record[9] == 1);

    /* Power loss discards a terminal record like any other. */
    boot(1);
    watchdog_record_fault_frame((uintptr_t)frame);
    boot(2 | 16);
    assert(record[0] == 1 && !record[1] && record[9] == 1);

    /* The carried count ages out after a healthy stretch (finding 3): three
     * crashes weeks apart must not switch the watchdog off. The count this
     * boot REPORTS stays a boot fact. */
    boot(1); boot(2); boot(2);
    assert(record[9] == 2 && retained.count == 2);
    watchdog_record_uptime(WATCHDOG_COUNT_AGE_OUT_MS - 1);
    assert(retained.count == 2);
    watchdog_record_uptime(WATCHDOG_COUNT_AGE_OUT_MS);
    assert(retained.count == 0);
    watchdog_record_fill(record);
    assert(record[9] == 2);
    boot(2);
    assert(record[9] == 1);
    /* A boot loop never gets that far, and still counts up. */
    watchdog_record_uptime(1000); boot(2);
    watchdog_record_uptime(1000); boot(2);
    assert(record[9] == 3);

    puts("watchdog retained-record tests passed");
    return 0;
}
