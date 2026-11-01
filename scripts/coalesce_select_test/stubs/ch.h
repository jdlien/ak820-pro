/* verify-044: minimal host stand-in for ChibiOS ch.h (daily build of ch582f_ajazz.c). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define CH_CFG_ST_RESOLUTION 16
#define CH_CFG_ST_FREQUENCY  187500
typedef uint16_t systime_t;
typedef uint16_t sysinterval_t;
typedef uint32_t syssts_t;
typedef uint64_t time_conv_t;
typedef int32_t  msg_t;
#define MSG_OK 0
#define TIME_MS2I(msecs) ((sysinterval_t)((((time_conv_t)(msecs) * (time_conv_t)CH_CFG_ST_FREQUENCY) + 999) / 1000))
#define TIME_I2MS(i) ((uint32_t)((((time_conv_t)(i) * 1000) + CH_CFG_ST_FREQUENCY - 1) / CH_CFG_ST_FREQUENCY))
#define TIME_I2US(i) ((uint32_t)((((time_conv_t)(i) * 1000000) + CH_CFG_ST_FREQUENCY - 1) / CH_CFG_ST_FREQUENCY))
typedef struct ch_virtual_timer virtual_timer_t;
typedef void (*vtfunc_t)(virtual_timer_t *vtp, void *p);
struct ch_virtual_timer { int unused; };
systime_t     chVTGetSystemTimeX(void);
sysinterval_t chVTTimeElapsedSinceX(systime_t start);
static inline sysinterval_t chTimeDiffX(systime_t s, systime_t e) { return (sysinterval_t)(e - s); }
static inline syssts_t chSysGetStatusAndLockX(void) { return 0; }
static inline void chSysRestoreStatusX(syssts_t s) { (void)s; }
static inline void chSysLock(void) {}
static inline void chSysUnlock(void) {}
static inline void chSysLockFromISR(void) {}
static inline void chSysUnlockFromISR(void) {}
static inline void chVTObjectInit(virtual_timer_t *v) { (void)v; }
static inline void chVTSet(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
static inline void chVTSetI(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
#define osalSysLock()   chSysLock()
#define osalSysUnlock() chSysUnlock()
