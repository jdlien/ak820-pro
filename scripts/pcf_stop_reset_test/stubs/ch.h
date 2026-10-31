/* Host stand-in for ChibiOS's ch.h (verify-018). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define CH_CFG_ST_FREQUENCY 187500
typedef uint16_t systime_t;
typedef uint32_t sysinterval_t;
typedef uint32_t syssts_t;
typedef int32_t  msg_t;
#define MSG_OK       ((msg_t)0)
#define MSG_TIMEOUT  ((msg_t)-1)
#define TIME_MS2I(ms) ((sysinterval_t)((((uint64_t)(ms)) * CH_CFG_ST_FREQUENCY + 999u) / 1000u))
#define TIME_US2I(us) ((sysinterval_t)((((uint64_t)(us)) * CH_CFG_ST_FREQUENCY + 999999u) / 1000000u))
/* One thread, and the sim fires the RTC ISR only between firmware calls:
 * the lock has nothing to exclude. */
static inline void chSysLock(void) {}
static inline void chSysUnlock(void) {}
systime_t chVTGetSystemTimeX(void);
static inline sysinterval_t chTimeDiffX(systime_t a, systime_t b) { return (sysinterval_t)(uint16_t)(b - a); }
