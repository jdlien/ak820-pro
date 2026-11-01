/* Host stand-in for ChibiOS's ch.h: the types, the 16-bit system tick at
 * 187.5 kHz (the SN32 boards' chconf.h), the lock and the virtual timers that
 * ch582f_ajazz.c's dev build touches. Implemented by sim.c. */
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

#define TIME_MS2I(msecs) \
    ((sysinterval_t)((((time_conv_t)(msecs) * (time_conv_t)CH_CFG_ST_FREQUENCY) + (time_conv_t)999) / (time_conv_t)1000))
#define TIME_I2MS(interval) \
    ((uint32_t)((((time_conv_t)(interval) * (time_conv_t)1000) + (time_conv_t)CH_CFG_ST_FREQUENCY - (time_conv_t)1) / (time_conv_t)CH_CFG_ST_FREQUENCY))

#define TIME_I2US(interval) \
    ((uint32_t)((((time_conv_t)(interval) * (time_conv_t)1000000) + (time_conv_t)CH_CFG_ST_FREQUENCY - (time_conv_t)1) / (time_conv_t)CH_CFG_ST_FREQUENCY))
sysinterval_t chVTTimeElapsedSinceX(systime_t start);
typedef struct ch_virtual_timer virtual_timer_t;
typedef void (*vtfunc_t)(virtual_timer_t *vtp, void *p);
struct ch_virtual_timer {
    bool     armed;
    uint64_t deadline;   /* absolute, in the sim's 64-bit ticks */
    vtfunc_t fn;
    void    *arg;
};

systime_t chVTGetSystemTimeX(void);
static inline sysinterval_t chTimeDiffX(systime_t start, systime_t end) { return (sysinterval_t)((systime_t)(end - start)); }
syssts_t chSysGetStatusAndLockX(void);
void     chSysRestoreStatusX(syssts_t sts);
void     chSysLock(void);
void     chSysUnlock(void);
void     chSysLockFromISR(void);
void     chSysUnlockFromISR(void);
void     chVTObjectInit(virtual_timer_t *vtp);
void     chVTSet(virtual_timer_t *vtp, sysinterval_t delay, vtfunc_t vtfunc, void *par);
void     chVTSetI(virtual_timer_t *vtp, sysinterval_t delay, vtfunc_t vtfunc, void *par);
#define osalSysLock()   chSysLock()
#define osalSysUnlock() chSysUnlock()
