/* Host stand-in for ChibiOS's hal.h: the serial driver (input and output
 * queues of SERIAL_BUFFERS_SIZE = 128, platforms/chibios/boards/common/configs/
 * halconf.h), its event source and the system timer's counter. The UART behind
 * it is simulated in sim.c: bytes arrive at 115200 baud into the input queue
 * (a full queue drops the byte and raises SD_OVERRUN_ERROR, as
 * hal_serial_lld.c's serve_interrupt does), and the output queue drains at the
 * same rate; sdWrite blocks (sim time advances) while it is full, as the real
 * TIME_INFINITE write does. */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "ch.h"

#define SERIAL_BUFFERS_SIZE 128
typedef struct {
    uint8_t buf[SERIAL_BUFFERS_SIZE];
    size_t  head, count;
} io_queue_t;

typedef struct {
    uint32_t speed;
    uint8_t  UART_WordLength, UART_StopBits, UART_Parity, UART_FIFOControl,
             UART_AutoBaudControl, UART_Oversampling, UART_HalfDuplexMode;
} SerialConfig;
typedef struct {
    io_queue_t iqueue;
    io_queue_t oqueue;
    bool       started;
} SerialDriver;
extern SerialDriver SD2;
void   sdStart(SerialDriver *sd, const SerialConfig *cfg);
size_t sdWrite(SerialDriver *sd, const uint8_t *b, size_t n);
#define TIME_IMMEDIATE ((sysinterval_t)0)
size_t chnReadTimeout(SerialDriver *sd, uint8_t *b, size_t n, sysinterval_t timeout);
size_t oqGetEmptyI(io_queue_t *q);
size_t oqGetFullI(io_queue_t *q);

typedef uint32_t eventflags_t;
typedef uint32_t eventmask_t;
typedef struct { int unused; } event_source_t;
typedef struct { eventflags_t flags, wflags; bool registered; } event_listener_t;
event_source_t *chnGetEventSource(SerialDriver *sd);
void            chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f);
eventflags_t    chEvtGetAndClearFlags(event_listener_t *el);
#define EVENT_MASK(n)    ((eventmask_t)1 << (n))
#define SD_PARITY_ERROR  ((eventflags_t)32)
#define SD_FRAMING_ERROR ((eventflags_t)64)
#define SD_OVERRUN_ERROR ((eventflags_t)128)

uint32_t st_lld_get_counter(void);
