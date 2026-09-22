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
    puts("watchdog retained-record tests passed");
    return 0;
}
