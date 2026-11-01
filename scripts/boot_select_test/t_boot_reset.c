/* verify-002: the boot's default-slot selects reach a live CH582F.
 *
 * Linked against the REAL, unedited firmware files (by path, see build.sh):
 *   quantum/dip_switch.c                         dip_switch_init() / forced read
 *   keyboards/a_jazz/ak820pro/bt_ui.c            bt_ui_mode_slider(), bt_ui_resume_saved_profile()
 *   keyboards/a_jazz/ak820pro/bluetooth/ch582f_ajazz.c   the TX queue, pump, RX parser
 *   gen_dip_update_kb.c                          dip_switch_update_kb() copied verbatim from ak820pro.c
 *
 * The boot is replayed in quantum/keyboard.c's order: dip_switch_init()
 * (keyboard.c:520), bluetooth_init() (keyboard.c:542), then
 * keyboard_post_init_kb()'s kb_eeconfig_init() + bt_ui_resume_saved_profile()
 * (ak820pro.c:82-84), then the main loop's ch582_task().
 *
 * The module is modelled as a peer on the UART: it ACKs (61 0D 0A) each frame
 * ~2 ms after it lands, once its UART is "up", and logs every A6 select it
 * receives. In "live" mode (an MCU-only reset: WDT, sleep.c's
 * NVIC_SystemReset) it is up from t=0 and currently linked on slot 2; in
 * "cold" mode it ignores everything until module_up_at.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hal.h"
#include "quantum.h"
#include "gpio.h"
#include "connection.h"
#include "kb_eeconfig.h"
#include "ch582f_ajazz.h"
#include "bt_ui.h"
#undef printf

void dip_switch_init(void);
void bluetooth_init(void);

/* ---- HAL / QMK stubs ------------------------------------------------------ */
SerialDriver SD2;
bool         loop_acct_on = false;
static uint32_t now_ms = 0;
uint16_t timer_read(void) { return (uint16_t)now_ms; }
uint32_t timer_read32(void) { return now_ms; }
systime_t chVTGetSystemTimeX(void) { return (systime_t)((uint64_t)now_ms * CH_CFG_ST_FREQUENCY / 1000u); }
uint16_t timer_elapsed(uint16_t t) { return (uint16_t)((uint16_t)now_ms - t); }
uint32_t timer_elapsed32(uint32_t t) { return now_ms - t; }
void battery_5c_report(uint8_t d) { (void)d; }
void health_note_rx_malformed(void) {}
void chEvtRegisterMaskWithFlags(event_source_t *es, event_listener_t *el, eventmask_t m, eventflags_t f) { (void)es; (void)el; (void)m; (void)f; }
eventflags_t chEvtGetAndClearFlags(event_listener_t *el) { (void)el; return 0; }
void clear_keyboard(void) {}
static connection_host_t host = CONNECTION_HOST_NONE;
void connection_set_host_noeeprom(connection_host_t h) { host = h; }
void display_set_pair_hint(int16_t pct) { (void)pct; }
void display_draw_usb_logo(void) {}
void display_draw_bluetooth_logo(void) {}
void display_draw_2_4_g_logo(void) {}
void display_draw_windows_logo(void) {}
void display_draw_mac_logo(void) {}
void prof_switch(bool mac) { (void)mac; }
bool dip_switch_update_user(uint8_t index, bool active) { (void)index; (void)active; return true; } /* via keymap: layer only, returns true */

/* The slider on BT: B12 (dip index 1) pulled low = active; B13 (2.4G) and B1 high. */
static bool pin_level[3] = {true, false, true};
void gpio_set_pin_input_high(pin_t p) { (void)p; }
bool gpio_read_pin(pin_t p) { return pin_level[p]; }

/* kb_eeconfig: zero before kb_eeconfig_init() (the .bss kb_config), the saved
 * slot after it. Getter validates as kb_eeconfig.c:95-101 does. */
static uint8_t ee_bt_profile = 0, ee_saved = 0;
static void    kb_eeconfig_init(void) { ee_bt_profile = ee_saved; }
uint8_t kb_eeconfig_get_bt_profile(void) {
    return (ee_bt_profile >= CH582_PROFILE_BT_1 && ee_bt_profile <= CH582_PROFILE_BT_3) ? ee_bt_profile : CH582_PROFILE_BT_1;
}
void kb_eeconfig_set_bt_profile(uint8_t p) { ee_bt_profile = p; }

/* ---- UART + module model ------------------------------------------------- */
static uint8_t rxq[4096];
static size_t  rx_h = 0, rx_t = 0;
static void    rx(const uint8_t *b, size_t n) { for (size_t i = 0; i < n; i++) { rxq[rx_t] = b[i]; rx_t = (rx_t + 1) % sizeof rxq; } }
size_t chnReadTimeout(SerialDriver *sdp, uint8_t *b, size_t n, sysinterval_t t) {
    (void)sdp; (void)t; size_t k = 0;
    while (k < n && rx_h != rx_t) { b[k++] = rxq[rx_h]; rx_h = (rx_h + 1) % sizeof rxq; }
    return k;
}
void sdStart(SerialDriver *sdp, const SerialConfig *cfg) { (void)sdp; (void)cfg; }

static bool     module_live;          /* UART up and listening */
static uint32_t module_up_at;         /* cold mode: when it starts listening */
static uint8_t  module_slot;          /* 1..3; the slot it is on / attempting */
static bool     module_linked;
static bool     module_ignore_mid_attempt = false;  /* speculative variant */
static uint32_t module_attempt_since;
static uint8_t  selects_rx[64];
static uint32_t selects_at[64];
static int      n_selects_rx;
static int      link_drops;
/* pending module output */
static struct { uint32_t at; uint8_t b[3]; } outq[256];
static int n_out;
static void sched(uint32_t at, uint8_t a, uint8_t b, uint8_t c) { outq[n_out].at = at; outq[n_out].b[0] = a; outq[n_out].b[1] = b; outq[n_out].b[2] = c; n_out++; }
static void module_flush(void) {
    for (int i = 0; i < n_out;) {
        if (outq[i].at <= now_ms) { rx(outq[i].b, 3); outq[i] = outq[--n_out]; }
        else i++;
    }
}
size_t sdWrite(SerialDriver *sdp, const uint8_t *b, size_t n) {
    (void)sdp;
    bool up = module_live || now_ms >= module_up_at;
    if (!up) return n;                         /* dropped on the floor: UART not up */
    if (n >= 3 && b[0] == 0xA6) {
        sched(now_ms + 2, 0x61, 0x0D, 0x0A);   /* the per-frame ACK */
        uint8_t p = b[1];
        if (p >= CH582_PROFILE_BT_1 && p <= CH582_PROFILE_BT_3) {
            selects_at[n_selects_rx] = now_ms; selects_rx[n_selects_rx++] = p;
            uint8_t slot = (uint8_t)(p - 0x30);
            bool attempting = !module_linked && now_ms - module_attempt_since < 2000;
            if (module_ignore_mid_attempt && attempting && slot != module_slot) return n;
            if (slot != module_slot || !module_linked) {
                if (module_linked) link_drops++;
                module_linked        = false;
                module_slot          = slot;
                module_attempt_since = now_ms;
                sched(now_ms + 5, 0x5B, 0x33, (uint8_t)(0x5B + 0x33));   /* connect ATTEMPT */
            }
        }
    } else if (n >= 3) {
        sched(now_ms + 2, 0x61, 0x0D, 0x0A);
    }
    return n;
}

static void run(uint32_t ms) {
    for (uint32_t i = 0; i < ms; i++) { module_flush(); ch582_task(); now_ms++; }
}

/* The firmware's own boot, in keyboard.c's order. */
static void boot(uint8_t saved_slot) {
    ee_saved = saved_slot;
    dip_switch_init();            /* keyboard.c:520 -- forced read, every index */
    bluetooth_init();             /* keyboard.c:542 */
    kb_eeconfig_init();           /* ak820pro.c:82 */
    bt_ui_resume_saved_profile(); /* ak820pro.c:84 */
}

static void print_selects(const char *label) {
    printf("%s: module received", label);
    for (int i = 0; i < n_selects_rx; i++) printf(" A6 %02X@%ums", selects_rx[i], selects_at[i]);
    printf("  (link drops: %d, module ends on slot %u)\n", link_drops, module_slot);
}

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "live";
    int failures = 0;
    if (!strcmp(mode, "live") || !strcmp(mode, "live-ignore")) {
        /* MCU-only reset: module up throughout, linked to the Mac on slot 2,
         * and the saved slot in EEPROM is slot 2. */
        module_live   = true;
        module_slot   = 2;
        module_linked = true;
        module_ignore_mid_attempt = !strcmp(mode, "live-ignore");
        boot(CH582_PROFILE_BT_2);
        run(3000);
        print_selects(mode);
        printf("  board: target_slot=%u select_state=%s host=%s\n", ch582_get_target_slot(),
               ch582_select_state() == CH582_SEL_ACKED ? "ACKED" : ch582_select_state() == CH582_SEL_PENDING ? "PENDING" : "LOST",
               host == CONNECTION_HOST_BLUETOOTH ? "BT" : "other");
        bool slot1_first = n_selects_rx > 0 && selects_rx[0] == CH582_PROFILE_BT_1;
        if (slot1_first) {
            printf("  BUG: a live module linked on slot 2 was sent slot 1 before the saved slot 2\n");
            failures++;
        }
        if (!strcmp(mode, "live-ignore") && module_slot != 2 && ch582_get_target_slot() == 2 && ch582_select_state() == CH582_SEL_ACKED)
            printf("  (speculative) board shows slot 2 ACKED and stops retrying while the module sits on slot %u\n", module_slot);
    } else {
        /* Cold boot: module not listening until module_up_at ms. */
        module_live  = false;
        module_up_at = (uint32_t)(argc > 2 ? atoi(argv[2]) : 400);
        module_slot  = 0;
        boot(CH582_PROFILE_BT_2);
        run(3000);
        print_selects("cold");
        if (n_selects_rx > 0 && selects_rx[0] == CH582_PROFILE_BT_1) {
            printf("  slot 1 reached the module at cold boot too (module up at %u ms)\n", module_up_at);
            failures++;
        }
    }
    return failures ? 1 : 0;
}
