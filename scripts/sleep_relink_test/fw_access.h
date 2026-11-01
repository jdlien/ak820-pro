#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct {
    int      tx_head, tx_tail, tx_in_flight, tx_retries;
    uint8_t  tx_len[24];
    uint8_t  tx_data[24][18];
    int      pa_kind, pa_tries, conn_state;
    bool     is_connected, is_pairing, usb_mode, module_alive, connect_requested, battery_poll_held;
    uint8_t  battery_level, host_leds, requested_profile;
    uint16_t battery_reports;
    bool     dev;
    int      r81_state, r81_len, r81_resp_n, r81_req_full, r91_ack_window, r81_depth;
    int      lc_st, lc_got_bits, lc_sec_bits, lc_sec_profile;
    uint32_t lc_frames, lc_preambles, lcm_applied, lcm_rejected;
    uint32_t lcc_applied, lcc_rejected, lcc_pending;
    uint32_t r81_ok, r81_dispatched, r91_sent;
    uint16_t lc_aborts[9];
    uint32_t r81_counts[9];
} fw_view_t;
void fw_snapshot(fw_view_t *v);
