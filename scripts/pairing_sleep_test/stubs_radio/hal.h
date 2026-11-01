#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
typedef uint32_t eventflags_t;
typedef uint32_t eventmask_t;
typedef int32_t  msg_t;
typedef uint32_t sysinterval_t;
typedef uint16_t systime_t;
typedef struct { int dummy; } event_listener_t;
typedef struct { int dummy; } event_source_t;
typedef struct {
    uint32_t speed;
    uint8_t UART_WordLength, UART_StopBits, UART_Parity, UART_FIFOControl, UART_AutoBaudControl, UART_Oversampling, UART_HalfDuplexMode;
} SerialConfig;
typedef struct { event_source_t es; } SerialDriver;
extern SerialDriver SD2;
#define SD_OVERRUN_ERROR 0x80u
#define SD_FRAMING_ERROR 0x20u
#define SD_PARITY_ERROR  0x10u
#define EVENT_MASK(n) ((eventmask_t)1 << (n))
#define TIME_IMMEDIATE ((sysinterval_t)0)
#define CH_CFG_ST_FREQUENCY 187500u
#define TIME_MS2I(ms) ((sysinterval_t)(((uint32_t)(ms) * CH_CFG_ST_FREQUENCY + 999u) / 1000u))
systime_t chVTGetSystemTimeX(void);   /* world_sys.c: the simulated ms, in ticks */
#define chnGetEventSource(sdp) (&(sdp)->es)
void sdStart(SerialDriver *sdp, const SerialConfig *cfg);
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t);
size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n);
void chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f);
eventflags_t chEvtGetAndClearFlags(event_listener_t *el);
