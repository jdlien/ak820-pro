/* Host stand-in for ChibiOS's hal.h (verify-018): just enough for rtc.c, the
 * real SN32 RTC LLD (hal_rtc_lld.c) and the real ChibiOS hal_rtc.c. The RTC
 * types come from the real hal_rtc.h / hal_rtc_lld.h. */
#pragma once
#include "ch.h"
#include <time.h>
#include <string.h>
#include <stdio.h>
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif
#define HAL_USE_RTC  TRUE
#define SN32_HAS_RTC TRUE

/* SN32 RTC registers. SECCNTV writes and SECCNT reads go through the sim:
 * writing SECCNTV restarts the counter (phase-0 fact T0.1), and SECCNT is
 * the ILRC cycles since the last restart. */
typedef struct {
    volatile uint32_t CTRL, IE, RIS, IC, CLKS;
    volatile uint32_t SECCNTV_reg[1];
    volatile uint32_t SECCNT_reg[1];
} SN_RTC_Type;
int sim_seccntv_touch(void);
int sim_seccnt_read(void);
#define SECCNTV SECCNTV_reg[sim_seccntv_touch()]
#define SECCNT  SECCNT_reg[sim_seccnt_read()]
extern SN_RTC_Type sim_rtc_regs;
#define SN_RTC (&sim_rtc_regs)

typedef struct { volatile uint32_t FRMNO; } SN_USB_Type;
extern SN_USB_Type sim_usb_regs;
#define SN_USB (&sim_usb_regs)

typedef struct { volatile uint32_t ISER[1]; } NVIC_Type;
extern NVIC_Type sim_nvic;
#define NVIC (&sim_nvic)
#define CT16B1_IRQn 18
static inline void NVIC_DisableIRQ(int n) { sim_nvic.ISER[0] &= ~(1u << n); }
static inline void NVIC_EnableIRQ(int n)  { sim_nvic.ISER[0] |=  (1u << n); }

/* OSAL bits the RTC LLD and hal_rtc.c use. */
static inline syssts_t osalSysGetStatusAndLockX(void) { return 0; }
static inline void osalSysRestoreStatusX(syssts_t s) { (void)s; }
#define osalDbgAssert(c, m) do { if (!(c)) { fprintf(stderr, "osalDbgAssert: %s\n", m); __builtin_trap(); } } while (0)
#define osalDbgCheck(c)     do { if (!(c)) { fprintf(stderr, "osalDbgCheck\n"); __builtin_trap(); } } while (0)
#define OSAL_IRQ_HANDLER(id) void id(void)
#define OSAL_IRQ_PROLOGUE()
#define OSAL_IRQ_EPILOGUE()
#define SN32_RTC_HANDLER     sim_sn32_rtc_handler
#define SN32_RTC_NUMBER      0
static inline void sys1EnableRTC(void) {}
static inline void nvicEnableVector(int n, int p) { (void)n; (void)p; }

#include "hal_rtc.h"   /* the real ChibiOS header; it includes the real hal_rtc_lld.h */
void sim_sn32_rtc_handler(void);

/* USB: the board is off USB in every scenario here. */
typedef enum { USB_UNINIT = 0, USB_STOP = 1, USB_READY = 2, USB_SELECTED = 3, USB_ACTIVE = 4, USB_SUSPENDED = 5 } usbstate_t;
typedef struct { usbstate_t state; } USBDriver;
extern USBDriver USBD1;
#define usbGetDriverStateI(u) ((u)->state)

/* The bit-banged I2C: the sim's PCF8563 answers. */
#define A14 14
#define A15 15
typedef struct { bool addr10; int scl; int sda; void (*delay)(void); } I2CConfig;
typedef struct { int state; } I2CDriver;
extern I2CDriver I2CD1;
void  i2cStart(I2CDriver *d, const I2CConfig *c);
void  i2cStop(I2CDriver *d);
msg_t i2cMasterTransmitTimeout(I2CDriver *d, uint16_t addr, const uint8_t *tx, size_t ntx,
                               uint8_t *rx, size_t nrx, sysinterval_t timeout);
