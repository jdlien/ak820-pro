/* verify-044: minimal host stand-in for ChibiOS hal.h: a serial driver whose
 * writes are logged (test.c) and whose reads come from a byte buffer the test fills. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "ch.h"
typedef struct { uint32_t speed; uint8_t UART_WordLength, UART_StopBits, UART_Parity, UART_FIFOControl,
                 UART_AutoBaudControl, UART_Oversampling, UART_HalfDuplexMode; } SerialConfig;
typedef struct { size_t q; } io_queue_t;
typedef struct { io_queue_t iqueue, oqueue; } SerialDriver;
extern SerialDriver SD2;
void   sdStart(SerialDriver *sd, const SerialConfig *cfg);
size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n);
#define TIME_IMMEDIATE ((sysinterval_t)0)
size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, sysinterval_t t);
static inline size_t oqGetEmptyI(io_queue_t *q) { (void)q; return 128; }
static inline size_t oqGetFullI(io_queue_t *q) { (void)q; return 0; }
typedef uint32_t eventflags_t;
typedef uint32_t eventmask_t;
typedef struct { int unused; } event_source_t;
typedef struct { int unused; } event_listener_t;
static inline event_source_t *chnGetEventSource(SerialDriver *sd) { static event_source_t es; (void)sd; return &es; }
static inline void chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f) { (void)es; (void)el; (void)m; (void)f; }
static inline eventflags_t chEvtGetAndClearFlags(event_listener_t *el) { (void)el; return 0; }
#define EVENT_MASK(n)    ((eventmask_t)1 << (n))
#define SD_PARITY_ERROR  ((eventflags_t)32)
#define SD_FRAMING_ERROR ((eventflags_t)64)
#define SD_OVERRUN_ERROR ((eventflags_t)128)
uint32_t st_lld_get_counter(void);
