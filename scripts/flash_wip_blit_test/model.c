/* verify-014's hardware model: the SPI0/SPI1 registers, a SPI NOR flash
 * (PY25Q128HA-like), the GC9107 panel's GRAM, and the flash->LCD DMA.
 *
 * The flash model follows standard SPI NOR behaviour: while a sector erase or
 * page program is running (status bit 0, WIP), the chip accepts only RDSR
 * (0x05); any other command, READ included, is ignored and DO stays high-Z.
 * What a high-Z MISO reads as is MODEL_HIZ (0xFF by default: the SN32 pin
 * pull-up is on at reset; set MODEL_HIZ=0 to model a line that idles low). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "model.h"

model_spi_t  model_spi[2];
model_sys1_t model_sys1;
model_pfpa_t model_pfpa;
SPIDriver    SPID0 = {SPI_STOP, 0}, SPID1 = {SPI_STOP, 1};
volatile uint8_t loop_stall_mark;

/* ---------------- time ---------------- */
static uint32_t now_us;
void     model_advance_us(uint32_t us) { now_us += us; }
uint32_t model_now_us(void) { return now_us; }
uint32_t st_lld_get_counter(void) { return now_us / 5u; }
void     wait_ms(uint32_t ms) { now_us += ms * 1000u; }

/* ---------------- flash chip ---------------- */
#define FLASH_SIZE 0x1000000u
uint8_t model_flash[FLASH_SIZE];
uint8_t model_hiz = 0xFF;
static int      f_cs = 1;
static uint8_t  f_cmd;
static uint32_t f_n, f_addr;
static bool     f_ignored, f_wel, f_wip;
static uint8_t  f_kind;              /* 0x20 erase, 0x02 program */
static uint32_t f_op_addr, f_done_us;
static uint8_t  f_pp[256];
static uint32_t f_pp_len;
uint32_t model_erase_us   = 45000u;  /* a 4K sector erase (the code says 50-300 ms; 45 ms is optimistic) */
uint32_t model_program_us = 1000u;   /* a page program */
model_flash_stats_t model_fstats;

static void f_poll(void) {
    if (f_wip && (int32_t)(now_us - f_done_us) >= 0) {
        if (f_kind == 0x20) memset(&model_flash[f_op_addr & ~0xFFFu], 0xFF, 4096);
        else for (uint32_t i = 0; i < f_pp_len; i++) model_flash[(f_op_addr & ~0xFFu) | ((f_op_addr + i) & 0xFFu)] &= f_pp[i];
        f_wip = false;
    }
}
bool model_flash_wip(void) { f_poll(); return f_wip; }

static uint8_t f_xfer(uint8_t mosi) {
    if (f_cs) return model_hiz;
    f_poll();
    uint8_t miso = model_hiz;
    if (f_n == 0) {
        f_cmd = mosi;
        f_addr = 0;
        f_ignored = f_wip && mosi != 0x05;
        if (f_ignored) {
            model_fstats.ignored_cmds++;
            if (mosi == 0x03) model_fstats.ignored_reads++;
        }
    } else if (!f_ignored) {
        switch (f_cmd) {
            case 0x05: miso = (uint8_t)((f_wip ? 1u : 0u) | (f_wel ? 2u : 0u)); break;
            case 0x9F: miso = f_n == 1 ? 0x85 : f_n == 2 ? 0x20 : 0x18; break;
            case 0x03:
                if (f_n <= 3) f_addr = (f_addr << 8) | mosi;
                else { miso = model_flash[f_addr % FLASH_SIZE]; f_addr++; }
                break;
            case 0x20: case 0x02:
                if (f_n <= 3) f_addr = (f_addr << 8) | mosi;
                else if (f_cmd == 0x02 && f_n - 4 < 256) { f_pp[f_n - 4] = mosi; f_pp_len = f_n - 3; }
                break;
            default: break;
        }
    }
    f_n++;
    return miso;
}
static void f_cs_edge(int v) {
    if (v == f_cs) return;
    f_cs = v;
    if (!v) { f_n = 0; f_ignored = false; f_pp_len = 0; return; }
    /* CS rising: a write-class command executes now. */
    if (f_ignored || f_n == 0) return;
    if (f_cmd == 0x06) f_wel = true;
    else if ((f_cmd == 0x20 && f_n == 4) || (f_cmd == 0x02 && f_n >= 5)) {
        if (!f_wel) return;
        f_wel = false;
        f_wip = true;
        f_kind = f_cmd;
        f_op_addr = f_addr;
        f_done_us = now_us + (f_cmd == 0x20 ? model_erase_us : model_program_us);
        if (f_cmd == 0x20) model_fstats.erases++; else model_fstats.programs++;
    }
}

/* ---------------- panel ---------------- */
uint16_t model_fb[MODEL_FB_H][MODEL_FB_W];
static int      p_cs = 1, p_dc = 1;
static uint8_t  p_cmd, p_argn, p_args[4], p_hi;
static bool     p_half;
static uint16_t p_xs, p_xe, p_ys, p_ye, p_cx, p_cy;
static void p_pixel(uint16_t px) {
    if (p_cy < MODEL_FB_H && p_cx < MODEL_FB_W) model_fb[p_cy][p_cx] = px;
    if (++p_cx > p_xe) { p_cx = p_xs; p_cy++; }
}
static void p_byte(uint8_t b) {
    if (p_cs) return;
    if (!p_dc) {
        p_cmd = b; p_argn = 0; p_half = false;
        if (b == 0x2C) { p_cx = p_xs; p_cy = p_ys; }
        return;
    }
    switch (p_cmd) {
        case 0x2A: case 0x2B:
            if (p_argn < 4) p_args[p_argn++] = b;
            if (p_argn == 4) {
                uint16_t s = (uint16_t)(p_args[0] << 8 | p_args[1]), e = (uint16_t)(p_args[2] << 8 | p_args[3]);
                if (p_cmd == 0x2A) { p_xs = s; p_xe = e; } else { p_ys = s; p_ye = e; }
            }
            break;
        case 0x2C:   /* CPU pixels: hi byte first */
            if (!p_half) { p_hi = b; p_half = true; }
            else { p_pixel((uint16_t)(p_hi << 8 | b)); p_half = false; }
            break;
        default: break;
    }
}

/* ---------------- the register slots ---------------- */
static int32_t  pend = -1;
static uint32_t slot_next;
static uint32_t rx_pending[2];
static int      last_writer = 0;
static void resolve(void) {
    if (pend < 0) return;
    uint32_t k = (uint32_t)pend;
    pend = -1;
    for (int s = 0; s < 2; s++) {
        if (model_spi[s].data_[k] != MODEL_SENTINEL) {   /* a write */
            uint8_t b = (uint8_t)model_spi[s].data_[k];
            if (s == 0) p_byte(b); else (void)f_xfer(b);
            rx_pending[s]++;
            last_writer = s;
            return;
        }
    }
    /* a read: consume from the SPI that has something */
    if (rx_pending[last_writer]) rx_pending[last_writer]--;
    else if (rx_pending[!last_writer]) rx_pending[!last_writer]--;
}
static void fill_stat(uint32_t k) {
    for (int s = 0; s < 2; s++) {
        model_spi[s].stat_[k].TX_FULL  = 0;
        model_spi[s].stat_[k].BUSY     = 0;
        model_spi[s].stat_[k].RX_EMPTY = rx_pending[s] == 0;
    }
}
uint32_t model_data_acc(void) {
    resolve();
    uint32_t k = slot_next++ % MODEL_SLOTS;
    model_spi[0].data_[k] = model_spi[1].data_[k] = MODEL_SENTINEL;
    pend = (int32_t)k;
    return k;
}
uint32_t model_stat_acc(void) {
    resolve();
    uint32_t k = slot_next++ % MODEL_SLOTS;
    fill_stat(k);
    return k;
}

/* ---------------- GPIO ---------------- */
void gpio_set_pin_output(pin_t p) { (void)p; }
void gpio_write_pin(pin_t p, int v) {
    resolve();
    if (p == A13) f_cs_edge(v ? 1 : 0);
    else if (p == B8) p_cs = v ? 1 : 0;
    else if (p == D14) p_dc = v ? 1 : 0;
}

/* ---------------- the SPI driver ---------------- */
void spiStart(SPIDriver *d, const SPIConfig *c) { (void)c; d->state = SPI_READY; }
void spiSend(SPIDriver *d, size_t n, const void *tx) {
    resolve();
    const uint8_t *b = tx;
    for (size_t i = 0; i < n; i++) { if (d == &SPID0) p_byte(b[i]); else (void)f_xfer(b[i]); }
}
void spiExchange(SPIDriver *d, size_t n, const void *tx, void *rx) {
    resolve();
    const uint8_t *t = tx;
    uint8_t *r = rx;
    for (size_t i = 0; i < n; i++) r[i] = d == &SPID0 ? (p_byte(t[i]), 0xFF) : f_xfer(t[i]);
}

/* The flash->LCD DMA: SPI1 clocks dummy bytes (DFETCH_EN), its RX feeds SPI0's
 * TX as 16-bit words. Bytes are stored LO first in flash; DL=0xF shifts the
 * word MSB first, so the panel sees (b1<<8)|b0. Completed synchronously at
 * Fire(): 660 B at 24 MHz is ~0.2 ms, three orders below an erase's WIP. */
static uint32_t dma_len;
void spiSN32FlashDmaPrepare(SPIDriver *lcd, SPIDriver *flash, uint32_t len) {
    (void)lcd; (void)flash;
    dma_len = len;
    model_spi[0].DMACTRL_b.DMAEN = 0;
    model_spi[0].DMACNT_b.CNT = (uint16_t)(len - 1u);
}
void spiSN32FlashDmaFire(SPIDriver *lcd, spi_sn32_dma_cb_t cb) {
    (void)lcd;
    resolve();
    model_fstats.dma_transfers++;
    bool busy_chip = model_flash_wip();
    if (busy_chip) model_fstats.dma_from_busy_chip++;
    for (uint32_t i = 0; i + 1 < dma_len; i += 2) {
        uint8_t b0 = f_xfer(0xFF), b1 = f_xfer(0xFF);
        p_pixel((uint16_t)(b1 << 8 | b0));
    }
    model_spi[0].CURCNT_b.CURCNT = (uint16_t)(dma_len - 1u);
    model_spi[0].DMACTRL_b.DMAEN = 0;
    now_us += dma_len / 3u;   /* ~24 Mbit/s */
    cb();
}
void spiSN32FlashDmaAbort(SPIDriver *lcd) { (void)lcd; model_fstats.aborts++; }
uint32_t spiSN32FlashDmaRescues(void) { return 0; }

/* ---------------- the rest lcd_bus.c links against ---------------- */
uint32_t watchdog_record_enter(uint8_t site) { (void)site; return 0; }
void     watchdog_record_leave(uint32_t *prev) { (void)prev; }
bool display_anim_admissible(void) { return false; }
bool display_anim_begin(void) { return false; }
void display_anim_end(void) {}
static uint8_t mt_blank[32];
const uint8_t *mt_glyph_large(uint8_t code) { (void)code; return mt_blank; }
const uint8_t *mt_glyph_regular(uint8_t code) { (void)code; return mt_blank; }

void model_reset(void) {
    memset(model_flash, 0xFF, sizeof model_flash);
    memset(model_fb, 0x55, sizeof model_fb);
    memset(&model_fstats, 0, sizeof model_fstats);
    f_cs = 1; f_wip = false; f_wel = false;
    for (int s = 0; s < 2; s++) {
        model_spi[s].CTRL0_b.FRESET = 0;
        rx_pending[s] = 0;
    }
    pend = -1;
}
