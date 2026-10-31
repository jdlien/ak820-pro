#pragma once
#include <stdarg.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    uint64_t now;            /* ILRC cycles since the model started */
    uint32_t reload;         /* the live SECCNTV */
    bool     locked, in_isr, verbose;
    void   (*lock_hook)(void);   /* one shot, run inside the next chSysLock() */
    uint32_t lock_count, isr_runs, matches, reload_writes, i2c_xfers;
    uint8_t  pcf_sec, pcf_min, pcf_hour, pcf_day, pcf_wday, pcf_mon, pcf_year;
} hw_t;
extern hw_t hw;

void hw_reset(void);
void hw_advance(uint64_t cycles);
void hw_log(const char *fmt, ...);
