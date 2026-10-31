/* Host stub of ChibiOS's hal.h for the RTC path only. It supplies the
 * platform pieces (register block, OSAL lock, IRQ macros) and then includes
 * the REAL hal_rtc.h (which includes the REAL SN32 hal_rtc_lld.h), so the
 * real hal_rtc.c and hal_rtc_lld.c compile unmodified against it.
 *
 * The register block is a simulation: SN_RTC goes through sim_rtc_regs(),
 * which refreshes SECCNT from the simulated board time on every access. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include <assert.h>

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

#define HAL_USE_RTC  TRUE
#define SN32_HAS_RTC TRUE

typedef struct {
    volatile uint32_t CTRL;     /* 0x00 */
    volatile uint32_t CLKS;     /* 0x04 */
    volatile uint32_t IE;       /* 0x08 */
    volatile uint32_t RIS;      /* 0x0C */
    volatile uint32_t IC;       /* 0x10 */
    volatile uint32_t SECCNTV;  /* 0x14 */
    volatile uint32_t SECCNT;   /* 0x18 */
} SN_RTC_Type;

SN_RTC_Type *sim_rtc_regs(void);
#define SN_RTC (sim_rtc_regs())

/* OSAL: a lock is PRIMASK on the M0. The sim defers a tick that lands inside
 * one until the restore (none does in this model: time only advances inside
 * the calendar decode, which runs unlocked). */
typedef uint32_t syssts_t;
syssts_t sim_lock(void);
void     sim_restore(syssts_t s);
#define osalSysGetStatusAndLockX()  sim_lock()
#define osalSysRestoreStatusX(s)    sim_restore(s)
#define osalDbgAssert(c, m)         assert((c) && m)
#define osalDbgCheck(c)             assert(c)

#define OSAL_IRQ_HANDLER(id)  void id(void)
#define OSAL_IRQ_PROLOGUE()
#define OSAL_IRQ_EPILOGUE()
#define SN32_RTC_HANDLER      sim_rtc_irq_handler
#define SN32_RTC_NUMBER       0
#define sys1EnableRTC()       ((void)0)
#define nvicEnableVector(n, p) ((void)(n), (void)(p))

#include "hal_rtc.h"   /* the real one, from lib/chibios/os/hal/include */
