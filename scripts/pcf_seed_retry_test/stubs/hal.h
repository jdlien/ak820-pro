/* Host stand-in for ChibiOS's hal.h: the RTC, I2C, USB and NVIC pieces rtc.c
 * touches. The RTC calendar semantics copy ChibiOS's hal_rtc.c (the
 * conversions) and the SN32 LLD (RTC/hal_rtc_lld.c: a software time_t
 * advanced by the second interrupt); the sim supplies the bodies. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include "ch.h"

typedef int32_t msg_t;
#define MSG_OK       ((msg_t)0)
#define MSG_TIMEOUT  ((msg_t)-1)
#define MSG_RESET    ((msg_t)-2)

/* ---- RTC (ChibiOS hal_rtc.h + the SN32 LLD) ---- */
#define RTC_BASE_YEAR 1980U
typedef struct {
    uint32_t year : 8;
    uint32_t month : 4;
    uint32_t dstflag : 1;
    uint32_t dayofweek : 3;
    uint32_t day : 5;
    uint32_t millisecond : 27;
} RTCDateTime;

typedef struct RTCDriver RTCDriver;
typedef enum { RTC_EVENT_SECOND = 0 } rtcevent_t;
typedef void (*rtccb_t)(RTCDriver *rtcp, rtcevent_t event);
struct RTCDriver {
    rtccb_t  callback;
    uint32_t period;
};
extern RTCDriver RTCD1;

void     rtcSetTime(RTCDriver *rtcp, const RTCDateTime *timespec);
void     rtcGetTime(RTCDriver *rtcp, RTCDateTime *timespec);
void     rtcSetCallback(RTCDriver *rtcp, rtccb_t callback);
void     rtcConvertDateTimeToStructTm(const RTCDateTime *timespec, struct tm *timp, uint32_t *tv_msec);
void     rtcConvertStructTmToDateTime(const struct tm *timp, uint32_t tv_msec, RTCDateTime *timespec);
void     rtc_lld_set_period(RTCDriver *rtcp, uint32_t period);
uint32_t rtc_lld_get_period(RTCDriver *rtcp);
void     rtc_lld_add_secondsI(RTCDriver *rtcp, uint32_t seconds);
#define SN32_RTC_PERIOD_DEFAULT (32000UL)

typedef struct {
    volatile uint32_t SECCNT;
    volatile uint32_t RIS;
} SN_RTC_Type;
extern SN_RTC_Type sim_rtc_regs;
#define SN_RTC (&sim_rtc_regs)
#define mskRTC_SECIF (0x1u << 0)

typedef struct { volatile uint32_t FRMNO; } SN_USB_Type;
extern SN_USB_Type sim_usb_regs;
#define SN_USB (&sim_usb_regs)

/* ---- I2C (the fallback software driver's API) ---- */
typedef uint16_t i2caddr_t;
typedef struct {
    bool addr10;
    int  scl;
    int  sda;
    void (*delay)(void);
} I2CConfig;
typedef struct { int started; } I2CDriver;
extern I2CDriver I2CD1;
void  i2cStart(I2CDriver *i2cp, const I2CConfig *config);
void  i2cStop(I2CDriver *i2cp);
msg_t i2cMasterTransmitTimeout(I2CDriver *i2cp, i2caddr_t addr, const uint8_t *txbuf, size_t txbytes,
                               uint8_t *rxbuf, size_t rxbytes, sysinterval_t timeout);

/* ---- USB ---- */
typedef enum { USB_UNINIT = 0, USB_STOP, USB_READY, USB_SELECTED, USB_ACTIVE, USB_SUSPENDED } usbstate_t;
typedef struct { int dummy; } USBDriver;
extern USBDriver USBD1;
usbstate_t usbGetDriverStateI(USBDriver *usbp);

/* ---- NVIC ---- */
typedef struct { volatile uint32_t ISER[1]; } NVIC_Type;
extern NVIC_Type sim_nvic;
#define NVIC (&sim_nvic)
#define CT16B1_IRQn 5
static inline void NVIC_DisableIRQ(int n) { sim_nvic.ISER[0] &= ~(1u << n); }
static inline void NVIC_EnableIRQ(int n)  { sim_nvic.ISER[0] |= (1u << n); }
