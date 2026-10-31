#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef int32_t msg_t;
typedef uint32_t sysinterval_t;
typedef uint32_t systime_t;
#define MSG_OK 0
#define MSG_TIMEOUT -1
#define TIME_MS2I(x) ((sysinterval_t)(x))
#define TIME_US2I(x) ((sysinterval_t)((x) / 1000))
static inline void chSysLock(void) {}
static inline void chSysUnlock(void) {}
static inline systime_t chVTGetSystemTimeX(void) { return 0; }
static inline sysinterval_t chTimeDiffX(systime_t a, systime_t b) { return b - a; }
