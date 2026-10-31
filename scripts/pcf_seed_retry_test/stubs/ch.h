/* Host stand-in for ChibiOS's ch.h: only what rtc.c and sleep.h use. */
#pragma once
#include <stdint.h>
#include <stdbool.h>

typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;

/* The board's tick is ~187.5 kHz (16-bit, ~349 ms wrap); the exact rate does
 * not matter here, only that the macros exist. */
#define CH_CFG_ST_FREQUENCY 187500u
#define TIME_MS2I(ms) ((sysinterval_t)(((uint64_t)(ms) * CH_CFG_ST_FREQUENCY + 999u) / 1000u))
#define TIME_US2I(us) ((sysinterval_t)(((uint64_t)(us) * CH_CFG_ST_FREQUENCY + 999999u) / 1000000u))

extern int sim_lock_depth;
static inline void chSysLock(void)   { sim_lock_depth++; }
static inline void chSysUnlock(void) { sim_lock_depth--; }

systime_t chVTGetSystemTimeX(void);
static inline sysinterval_t chTimeDiffX(systime_t a, systime_t b) { return (sysinterval_t)(b - a); }
