/* Host stub of the ChibiOS HAL surface rtc.c touches. The RTC block is a
 * model with the T0.1 semantics (history/clock-sync/phase-0-facts.md): a
 * SECCNTV write resets SECCNT to 0. The test harness owns the timing. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <time.h>
#include "ch.h"

typedef struct {
    volatile uint32_t CTRL, IE, RIS, IC, CLKS, SECCNTV, SECCNT;
} sn_rtc_t;
extern sn_rtc_t sim_rtc;
#define SN_RTC (&sim_rtc)
typedef struct { volatile uint32_t FRMNO; } sn_usb_t;
extern sn_usb_t sim_usb;
#define SN_USB (&sim_usb)
#define mskRTC_SECIF 1u
#define mskRTC_SECIC 1u

typedef struct { volatile uint32_t ISER[1]; } nvic_t;
extern nvic_t sim_nvic;
#define NVIC (&sim_nvic)
#define CT16B1_IRQn 5
static inline void NVIC_DisableIRQ(int n) { sim_nvic.ISER[0] &= ~(1u << n); }
static inline void NVIC_EnableIRQ(int n)  { sim_nvic.ISER[0] |=  (1u << n); }
#define RTC_IRQn 25
static inline void NVIC_ClearPendingIRQ(int n) { (void)n; }

typedef uint32_t ioline_t;
typedef struct {
    bool addr10;
    ioline_t scl, sda;
    void (*delay)(void);
} I2CConfig;
typedef struct { int dummy; } I2CDriver;
extern I2CDriver I2CD1;
typedef uint8_t i2caddr_t;
void  i2cStart(I2CDriver *d, const I2CConfig *c);
void  i2cStop(I2CDriver *d);
msg_t i2cMasterTransmitTimeout(I2CDriver *d, i2caddr_t a, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx, sysinterval_t t);

typedef struct {
    uint32_t year;
    uint32_t month;
    uint32_t dstflag;
    uint32_t dayofweek;
    uint32_t day;
    uint32_t millisecond;
} RTCDateTime;
typedef unsigned rtcevent_t;
#define RTC_EVENT_SECOND 0
struct RTCDriver;
typedef void (*rtccb_t)(struct RTCDriver *rtcp, rtcevent_t event);
typedef struct RTCDriver { sn_rtc_t *rtc; uint32_t period; rtccb_t callback; } RTCDriver;
extern RTCDriver RTCD1;
void rtcSetTime(RTCDriver *r, const RTCDateTime *t);
void rtcGetTime(RTCDriver *r, RTCDateTime *t);
void rtcSetCallback(RTCDriver *r, rtccb_t cb);
void rtcConvertDateTimeToStructTm(const RTCDateTime *t, struct tm *tm, uint32_t *ms);
void rtcConvertStructTmToDateTime(const struct tm *tm, uint32_t ms, RTCDateTime *t);
void rtc_lld_set_period(RTCDriver *rtcp, uint32_t period);
uint32_t rtc_lld_get_period(RTCDriver *rtcp);
void rtc_lld_add_secondsI(RTCDriver *rtcp, uint32_t seconds);
#define SN32_RTC_PERIOD_DEFAULT 32000
#define SN32_RTC_PERIOD_MAX 0xFFFFFu
#include <string.h>
#define RTC_BASE_YEAR 1980U
typedef struct { int state; } USBDriver;
extern USBDriver USBD1;
#define USB_ACTIVE 4
int usbGetDriverStateI(USBDriver *u);
