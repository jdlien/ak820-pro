/* The firmware's CH582F driver, compiled VERBATIM: the file is #included by
 * its absolute path, unedited. The only additions are around it:
 *   - every static it defines (file scope and function scope) is placed in
 *     the sections __DATA,__fwdata / __DATA,__fwbss, so the harness can put
 *     the driver back to its power-on state before each fuzz input (the
 *     driver's state is file-static; libFuzzer runs inputs in one process);
 *   - read-only accessors after it, for the harness's invariant checks. */
#pragma clang section bss = "__DATA,__fwbss" data = "__DATA,__fwdata"
#include FW_CH582_C
#pragma clang section bss = "" data = ""

#include "fw_access.h"

void fw_snapshot(fw_view_t *v) {
    memset(v, 0, sizeof *v);
    v->tx_head = tx_head;
    v->tx_tail = tx_tail;
    v->tx_in_flight = tx_in_flight;
    v->tx_retries = tx_retries;
    for (int i = 0; i < CH582_TXQ_LEN; i++) {
        v->tx_len[i] = tx_q[i].len;
        memcpy(v->tx_data[i], tx_q[i].data, sizeof tx_q[i].data);
    }
    v->pa_kind = (int)pa.kind;
    v->pa_tries = pa.tries;
    v->conn_state = (int)conn_state;
    v->is_connected = is_module_connected;
    v->is_pairing = is_pairing;
    v->usb_mode = usb_mode;
    v->module_alive = module_alive;
    v->battery_level = battery_level;
    v->battery_reports = battery_reports;
    v->host_leds = host_leds;
    v->requested_profile = requested_profile;
    v->connect_requested = connect_requested;
    v->battery_poll_held = battery_poll_held;
#ifdef AK820_DEV_HOOKS
    v->dev = true;
    v->r81_state = (int)r81.state;
    v->r81_len = r81.len;
    v->r81_resp_n = r81_resp.n;
    v->r81_req_full = r81_req.full;
    v->r91_ack_window = r91_ack_window;
    v->r81_depth = r81_depth;
    v->lc_st = lockchan.st;
    v->lc_got_bits = lockchan.got_bits;
    v->lc_sec_bits = lockchan.sec_bits;
    v->lc_sec_profile = lockchan.sec_profile;
    v->lc_frames = lockchan.frames;
    v->lc_preambles = lockchan.preambles;
    v->lcm_applied = lcm_applied;
    v->lcm_rejected = lcm_rejected;
    v->lcc_applied = lcc.applied;
    v->lcc_rejected = lcc.rejected;
    v->lcc_pending = lcc.pending;
    v->r81_ok = r81.ok;
    v->r81_dispatched = r81_dispatched;
    v->r91_sent = r91_sent_tx;
    memcpy(v->lc_aborts, lockchan.aborts, sizeof v->lc_aborts);
    const uint32_t rc[9] = {r81.ok, r81.stale, r81.forbidden, r81.badenv, r81.badsum, r81.taint, r81.lifetime, r81.busy, r81_drops};
    memcpy(v->r81_counts, rc, sizeof rc);
#else
    v->dev = false;
#endif
}
