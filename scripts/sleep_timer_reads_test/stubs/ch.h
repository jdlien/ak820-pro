/* Host stub of the ChibiOS kernel surface that sleep.c, power.c and QMK's
 * platforms/chibios/timer.c use. The system time is the SN32 port's: a 16-bit
 * counter (CT16B5) at 187.5 kHz. TIME_I2MS keeps ChibiOS's exact arithmetic
 * (chtime.h:255, time_conv_t = uint64_t) but counts each conversion: on the
 * M0 that is __aeabi_lmul + __aeabi_uldivmod (the ELF). */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define CH_CFG_ST_RESOLUTION 16
#define CH_CFG_ST_FREQUENCY  187500u
typedef uint16_t systime_t;
typedef uint16_t sysinterval_t;
typedef uint32_t syssts_t;
typedef uint64_t time_conv_t;
typedef uint32_t time_msecs_t;

extern uint32_t host_ticks;           /* the free-running tick, unwrapped (test drives it) */
extern unsigned host_n_lock;          /* lock entries */
extern unsigned host_n_i2ms;          /* 64-bit conversions: one lmul + one uldivmod each on the M0 */
extern uint64_t host_div_iters;       /* __udivmoddi4's shift-subtract iterations, modelled */

static inline systime_t chVTGetSystemTimeX(void) { return (systime_t)host_ticks; }
static inline void chSysLock(void) { host_n_lock++; }
static inline void chSysUnlock(void) {}
static inline void chSysLockFromISR(void) {}
static inline void chSysUnlockFromISR(void) {}
static inline syssts_t chSysGetStatusAndLockX(void) { host_n_lock++; return 0; }
static inline void chSysRestoreStatusX(syssts_t s) { (void)s; }

static inline int host_clz64(uint64_t x) { int n = 0; if (!x) return 64; while (!(x & (1ull << 63))) { x <<= 1; n++; } return n; }
static inline time_msecs_t host_i2ms(time_conv_t interval) {
    host_n_i2ms++;
    time_conv_t num = interval * (time_conv_t)1000 + (time_conv_t)CH_CFG_ST_FREQUENCY - 1;
    /* libgcc's __udivmoddi4 on armv6-m (disassembled at 0x2a288 in the daily
     * ELF) loops clz(divisor) - clz(dividend) times, one quotient bit each. */
    int it = host_clz64(CH_CFG_ST_FREQUENCY) - host_clz64(num);
    if (it > 0) host_div_iters += (uint64_t)it;
    return (time_msecs_t)(num / (time_conv_t)CH_CFG_ST_FREQUENCY);
}
#define TIME_I2MS(interval) host_i2ms((time_conv_t)(interval))

typedef struct ch_virtual_timer { int dummy; } virtual_timer_t;
typedef void (*vtfunc_t)(struct ch_virtual_timer *, void *);
static inline void chVTObjectInit(virtual_timer_t *v) { (void)v; }
static inline void chVTSet(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
static inline void chVTSetI(virtual_timer_t *v, sysinterval_t d, vtfunc_t f, void *p) { (void)v; (void)d; (void)f; (void)p; }
