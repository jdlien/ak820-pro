/* Host stand-in for ChibiOS's hal.h: just what ch582f_ajazz.c touches. The
 * simulated UART behind these lives in harness.c. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    uint32_t speed;
    uint8_t  UART_WordLength, UART_StopBits, UART_Parity, UART_FIFOControl,
             UART_AutoBaudControl, UART_Oversampling, UART_HalfDuplexMode;
} SerialConfig;
typedef struct { int unused; } SerialDriver;
extern SerialDriver SD2;
void   sdStart(SerialDriver *sd, const SerialConfig *cfg);
size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n);
#define TIME_IMMEDIATE 0
size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, int timeout);

typedef uint32_t eventflags_t;
typedef uint32_t eventmask_t;
typedef struct { int unused; } event_source_t;
typedef struct { eventflags_t flags; } event_listener_t;
event_source_t *chnGetEventSource(SerialDriver *sd);
void            chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el,
                                           eventmask_t m, eventflags_t f);
eventflags_t    chEvtGetAndClearFlags(event_listener_t *el);
#define EVENT_MASK(n)    ((eventmask_t)1 << (n))
#define SD_PARITY_ERROR  ((eventflags_t)32)
#define SD_FRAMING_ERROR ((eventflags_t)64)
#define SD_OVERRUN_ERROR ((eventflags_t)128)
