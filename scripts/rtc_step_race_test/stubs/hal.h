/* Host stand-in for ChibiOS's hal.h, for verify-020: the SN32 RTC as a
 * register block the test's hardware model drives, the OS lock as a flag the
 * model watches (a pending RTC interrupt is taken when the lock drops), and
 * the real ChibiOS hal_rtc.h with the SN32 RTC LLD's header. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif
#define HAL_USE_RTC  TRUE
#define SN32_HAS_RTC TRUE

typedef struct {
    volatile uint32_t CTRL, CLKS, IE, RIS, IC, SECCNTV, SECCNT;
} SN_RTC_Type;
extern SN_RTC_Type fake_rtc;
#define SN_RTC (&fake_rtc)

typedef struct { volatile uint32_t FRMNO; } SN_USB_Type;
extern SN_USB_Type fake_usb;
#define SN_USB (&fake_usb)

/* OS lock model (hw_model.c). */
typedef uint32_t syssts_t;
typedef int32_t  msg_t;
typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;
#define MSG_OK      0
#define MSG_TIMEOUT -1
#define MSG_RESET   -2
void     hw_lock(void);
void     hw_unlock(void);
syssts_t hw_get_status_and_lock(void);
void     hw_restore_status(syssts_t s);
#define chSysLock()                   hw_lock()
#define chSysUnlock()                 hw_unlock()
#define osalSysGetStatusAndLockX()    hw_get_status_and_lock()
#define osalSysRestoreStatusX(s)      hw_restore_status(s)
#define osalDbgAssert(c, m)           ((void)0)
#define osalDbgCheck(c)               ((void)0)
#define OSAL_IRQ_HANDLER(id)          void id(void)
#define OSAL_IRQ_PROLOGUE()
#define OSAL_IRQ_EPILOGUE()
#define SN32_RTC_HANDLER              fake_rtc_irq_handler
#define SN32_RTC_NUMBER               23
#define nvicEnableVector(n, p)        ((void)0)
#define sys1EnableRTC()               ((void)0)
void fake_rtc_irq_handler(void);

systime_t     chVTGetSystemTimeX(void);
#define chTimeDiffX(a, b)             ((sysinterval_t)((b) - (a)))
#define TIME_MS2I(ms)                 ((sysinterval_t)(ms) * 10u)
#define TIME_US2I(us)                 ((sysinterval_t)(((us) + 99u) / 100u))

/* NVIC (the row ISR's mask in the PCF transaction). */
typedef enum { CT16B1_IRQn = 1, RTC_IRQn = 23 } IRQn_Type;
typedef struct { volatile uint32_t ISER[1]; } NVIC_Type;
extern NVIC_Type fake_nvic;
#define NVIC (&fake_nvic)
#define NVIC_DisableIRQ(n)            ((void)(n))
#define NVIC_EnableIRQ(n)             ((void)(n))
#define NVIC_ClearPendingIRQ(n)       ((void)(n))

/* Software I2C. */
typedef uint32_t ioline_t;
typedef struct {
    bool     addr10;
    ioline_t scl, sda;
    void   (*delay)(void);
} I2CConfig;
typedef struct { int dummy; } I2CDriver;
extern I2CDriver I2CD1;
void  i2cStart(I2CDriver *d, const I2CConfig *c);
void  i2cStop(I2CDriver *d);
msg_t i2cMasterTransmitTimeout(I2CDriver *d, uint8_t addr, const uint8_t *tx, size_t ntx,
                               uint8_t *rx, size_t nrx, sysinterval_t t);

/* USB driver state (the PCF writer's "on USB" test). */
typedef enum { USB_UNINIT = 0, USB_STOP, USB_READY, USB_SELECTED, USB_ACTIVE, USB_SUSPENDED } usbstate_t;
typedef struct { int dummy; } USBDriver;
extern USBDriver USBD1;
usbstate_t usbGetDriverStateI(USBDriver *u);

#include <string.h>
#include "hal_rtc.h"
