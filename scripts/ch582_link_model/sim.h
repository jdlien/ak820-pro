#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include "hal.h"

#define SIM_FAIL(...)                                                    \
    do {                                                                 \
        fprintf(stderr, "SIM_FAIL %s:%d: ", __FILE__, __LINE__);         \
        fprintf(stderr, __VA_ARGS__);                                    \
        fprintf(stderr, "\n");                                           \
        abort();                                                         \
    } while (0)

#define WIRE_MAX 4096
typedef struct {
    uint8_t  b;
    uint8_t  err;          /* UART error flags raised with this byte (a framing error, or an overrun before it) */
    uint64_t not_before;   /* subticks */
} wire_byte_t;

typedef struct {
    uint64_t T;            /* ticks at 187.5 kHz since the input began */
    uint32_t ms_off;       /* QMK's ms clock = T/187.5 + ms_off */
    uint16_t tick_off;     /* the 16-bit system time = T + tick_off */
    uint64_t auto_adv;     /* ticks added at each timer read (a drain's own time) */
    uint64_t read_cost;    /* ticks each serial read costs (+1 a byte): bytes and errors land mid-drain */
    uint8_t  pending_err;  /* attached to the next byte the input pushes */
    int      lock, in_isr;
    /* the line */
    int      wire_head[2], wire_n[2];
    int      wire_cur;                /* the stream the last byte came from */
    uint64_t rx_line_free;
    bool     rx_off;
    uint8_t  tx_fifo_buf[16];
    int      tx_fifo, tx_fifo_head;
    uint64_t tx_next_sub;
    uint64_t blocked_ticks;
    uint32_t writes, bytes_read, rx_dropped;
    /* the peer */
    bool     peer_ack, peer_ack91;
    uint32_t peer_ack_us;
    uint8_t  peer_buf[40];
    uint8_t  peer_need, peer_n;
    uint32_t peer_frames, peer_badsum, peer_junk, board_acks;
    uint8_t  host_kbd[8];
    uint32_t host_kbd_n;
    uint8_t  peer_last_a6;
    uint8_t  last_reply[32];
    bool     have_reply;
    uint32_t receipts;
    /* board side */
    uint32_t rx_malformed, batt_reports;
    uint8_t  batt_last;
    uint32_t raw_hid_usb, via_calls;
    bool     media_seen, clock_owned;
    uint32_t media_at;
    uint32_t text_sets, text_clears, pb_sets;
    uint16_t pb_pos, pb_dur;
    uint8_t  pb_state;
    uint32_t rtc_sets;
    uint8_t  rtc_status;
    wire_byte_t wire[2][WIRE_MAX];   /* 0: the input's bytes, 1: the peer's ACKs; last: not cleared */
} sim_t;
extern sim_t S;

void sim_reset(void);
void sim_advance(uint64_t ticks);
void sim_wire_push(uint8_t b, uint32_t gap_us);
void sim_wire_clear(void);
int  sim_wire_pending(void);
void sim_uart_error(eventflags_t f);
int  sim_wdt_depth(void);

#define MS_TICKS(ms) ((uint64_t)(ms) * 375u / 2u)
