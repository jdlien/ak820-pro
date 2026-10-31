/* The flash provisioning channel (plans/AUDIT-2026-10-31.md; first written as
 * the audit's verify-046, for F-015):
 *   F-015  an animation of up to ANIM_MAX (243) frames provisions; 132-243
 *          failed at the last sector, after the old one was erased;
 *   F-044  a CRC straight after FC_WRITE_END waits for the last page program
 *          (here 3 ms, longer than the 2 ms round trip) instead of reading the
 *          busy chip;
 *   F-001  one chip operation a main-loop pass (a flood of commands in one
 *          pass folds nothing more), and a CRC slice bounded by time.
 *
 * Compiles, verbatim (run.sh extracts them at build time):
 *   graphics/lcd_bus.c  FLASH_CMD_READ, ANIM_BASE..ANIM_MAX, the flash write path
 *                       (FLASH_CMD_WREN .. flash_crc32_acc), anim_count and
 *                       anim_read_header()
 *   hid_protocol.c      the flash channel's enum, CRC state, the pass budget,
 *                       fw_* state, flash_flush_page() and flash_command()
 * against a 16 MB model of the PY25Q128HA with real erase (to 0xFF) and program
 * (AND, wrapping in its page) semantics, timed: each SPI byte BYTE_US, an erase
 * ERASE_US and a program PROG_US busy, a READ while busy floating (0xFF). It
 * replays ak820ctl.c's cmd_write() (unlock, erase every sector, WRITE_BEGIN,
 * 27-byte WRITE_DATA, WRITE_END, on-device CRC, unlock off) with fcmd()'s
 * retry-on-BUSY, each attempt a host round trip (RTT_US) and a main-loop pass
 * of its own. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- stubs for what the extract calls ---------------------------------- */
typedef uint32_t pin_t;
#define A13 0x0Du
#define FLASH_CS A13
#define WDT_SCOPE(site) /* watchdog breadcrumbs: not modelled */
static void    gpio_write_pin(pin_t p, int v);
static void    spi1_xfer(uint8_t b);
static uint8_t spi1_rw(uint8_t b);
static void    bus_quiesce(void) {}
void           lcd_flash_init(void) {}
static bool    g_anim_on;
bool           anim_active(void) { return g_anim_on; }
enum { RTC_UNHANDLED = 0xFF };

/* ---- time ---------------------------------------------------------------- */
#define BYTE_US  100u     /* an SPI1 byte through the ChibiOS driver at this ISR load (the audit: 40-200 us) */
#define ERASE_US 50000u
#define PROG_US  3000u
#define RTT_US   2000u
static uint64_t sim_us;
typedef uint32_t systime_t;
typedef uint32_t sysinterval_t;
static systime_t chVTGetSystemTimeX(void) { return (systime_t)(sim_us / 10u); }   /* 100 kHz */
static sysinterval_t chTimeDiffX(systime_t a, systime_t b) { return (sysinterval_t)(b - a); }
#define TIME_MS2I(ms) ((sysinterval_t)((ms) * 100u))

#include "lcd.inc"
#include "hid.inc"

/* ---- the chip ----------------------------------------------------------- */
#define CHIP_SIZE 0x1000000u
static uint8_t *mem;
static bool     cs_low, wel;
static uint8_t  ccmd;
static uint32_t cn, caddr;
static uint64_t wip_until;
static bool     read_while_busy;   /* this READ began with the chip busy: it floats */
static bool     busy_now(void) { return sim_us < wip_until; }
static uint8_t  pg[256];
static uint32_t n_erases, n_programs;

static void die(const char *m, uint32_t a) { fprintf(stderr, "CHIP MODEL: %s at 0x%06X\n", m, a); abort(); }

static void gpio_write_pin(pin_t p, int v) {
    if (p != FLASH_CS) return;
    if (!v) { if (cs_low) die("CS low twice", 0); cs_low = true; cn = 0; caddr = 0; ccmd = 0; read_while_busy = busy_now(); return; }
    if (!cs_low) return;
    cs_low = false;
    if (ccmd == FLASH_CMD_WREN) { wel = true; return; }
    if (ccmd == FLASH_CMD_SEC_ERASE) {
        if (cn != 4 || !wel || busy_now()) die("bad erase", caddr);
        if (caddr < 0x1AA000u) die("erase of the stock LCD assets", caddr);
        if (caddr & 0xFFFu) die("unaligned erase", caddr);
        memset(mem + caddr, 0xFF, 4096); n_erases++; wel = false; wip_until = sim_us + ERASE_US;
        return;
    }
    if (ccmd == FLASH_CMD_PAGE_PROG) {
        uint32_t n = cn - 4;
        if (cn < 5 || !wel || busy_now()) die("bad program", caddr);
        if (caddr < 0x1AA000u) die("program of the stock LCD assets", caddr);
        for (uint32_t i = 0; i < n; i++) mem[(caddr & ~0xFFu) | ((caddr + i) & 0xFFu)] &= pg[i];
        n_programs++; wel = false; wip_until = sim_us + PROG_US;
    }
}
static uint8_t spi1_rw(uint8_t b) {
    if (!cs_low) die("byte with CS high", 0);
    uint32_t i = cn++;
    sim_us += BYTE_US;
    if (i == 0) { ccmd = b; return 0xFF; }
    switch (ccmd) {
        case FLASH_CMD_RDSR: return (uint8_t)((busy_now() ? 1 : 0) | (wel ? 2 : 0));
        case FLASH_CMD_JEDEC: return i == 1 ? 0x85 : i == 2 ? 0x60 : 0x18;
        case FLASH_CMD_READ: case FLASH_CMD_PAGE_PROG: case FLASH_CMD_SEC_ERASE:
            if (i <= 3) { caddr = (caddr << 8) | b; return 0xFF; }
            if (ccmd == FLASH_CMD_READ) return read_while_busy ? 0xFF : mem[(caddr + i - 4) & (CHIP_SIZE - 1)];
            if (ccmd == FLASH_CMD_PAGE_PROG && i - 4 < 256) pg[i - 4] = b;
            return 0xFF;
    }
    return 0xFF;
}
static void spi1_xfer(uint8_t b) { (void)spi1_rw(b); }

/* ---- ak820ctl.c, cmd_write() and fcmd(), replayed ------------------------ */
#define SECTOR 4096u
#define CHUNK  27
static const char *last_err;
static uint64_t    worst_cmd_us;   /* the longest one command took: a main-loop pass's share */
static uint32_t    err_at;
static int fcmd(uint8_t c, const uint8_t *args, int nargs, uint8_t *rep) {
    uint8_t p[32] = {0x07, 0x11, c};
    if (nargs) memcpy(&p[3], args, (size_t)nargs);
    for (int tries = 0; tries < 2000; tries++) {
        memcpy(rep, p, 32);
        sim_us += RTT_US;                    /* the host's round trip */
        flash_channel_pass_end();            /* a main-loop pass of its own */
        uint64_t t0 = sim_us;
        flash_command(rep, 32);              /* raw_hid_receive -> is_flash_cmd -> flash_command */
        uint64_t d = sim_us - t0;
        if (d > worst_cmd_us) worst_cmd_us = d;
        if (rep[3] != FS_BUSY) break;
    }
    if (rep[3] != FS_OK && rep[3] != FS_MORE) {
        last_err = rep[3] == FS_REFUSED ? "refused" : "other"; return -1;
    }
    return 0;
}
static int unlock(int on) { uint8_t a[1] = {(uint8_t)(on ? 1 : 0)}, r[32]; return fcmd(FC_UNLOCK, a, 1, r); }
static uint32_t crc32_of(const uint8_t *p, size_t n) {
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) { c ^= p[i]; for (int b = 0; b < 8; b++) c = (c >> 1) ^ (0xEDB88320u & (-(int32_t)(c & 1))); }
    return ~c;
}
static uint32_t erased_ok;
/* Returns 0 on success; on failure mirrors ak820ctl's early returns exactly. */
static int cmd_write(uint32_t addr, const uint8_t *buf, long sz, int do_unlock) {
    uint8_t rep[32];
    erased_ok = 0;
    if (do_unlock && unlock(1) < 0) return 1;
    unsigned nsec = (unsigned)((sz + SECTOR - 1) / SECTOR);
    for (unsigned i = 0; i < nsec; i++) {             /* erase_sectors() */
        uint32_t a = addr + i * SECTOR;
        uint8_t args[3] = {(uint8_t)(a >> 16), (uint8_t)(a >> 8), (uint8_t)a};
        if (fcmd(FC_ERASE, args, 3, rep) < 0) { err_at = a; return 1; }
        erased_ok++;
    }
    uint8_t args[3] = {(uint8_t)(addr >> 16), (uint8_t)(addr >> 8), (uint8_t)addr};
    if (fcmd(FC_WRITE_BEGIN, args, 3, rep) < 0) { err_at = addr; return 1; }
    for (long off = 0; off < sz;) {
        uint8_t a[1 + CHUNK];
        long n = sz - off; if (n > CHUNK) n = CHUNK;
        a[0] = (uint8_t)n; memcpy(&a[1], buf + off, (size_t)n);
        if (fcmd(FC_WRITE_DATA, a, 1 + (int)n, rep) < 0) { err_at = addr + (uint32_t)off; return 1; }
        off += n;
    }
    if (fcmd(FC_WRITE_END, NULL, 0, rep) < 0) return 1;
    uint8_t c[6] = {(uint8_t)(addr >> 16), (uint8_t)(addr >> 8), (uint8_t)addr,
                    (uint8_t)(sz >> 16), (uint8_t)(sz >> 8), (uint8_t)sz};
    if (fcmd(FC_CRC32, c, 6, rep) < 0) return 1;
    while (rep[3] == FS_MORE) if (fcmd(FC_CRC_NEXT, NULL, 0, rep) < 0) return 1;
    uint32_t got = ((uint32_t)rep[4] << 24) | ((uint32_t)rep[5] << 16) | ((uint32_t)rep[6] << 8) | rep[7];
    if (do_unlock) unlock(0);
    if (got != crc32_of(buf, (size_t)sz)) { last_err = "VERIFY FAILED"; return 1; }
    return 0;
}

/* ---- mkanim.py's file layout --------------------------------------------- */
static uint8_t *mkanim(unsigned frames, uint8_t seed, long *sz) {
    *sz = 0x100 + (long)frames * 0x8000;
    uint8_t *b = malloc((size_t)*sz);
    memset(b, 0, 0x100);
    b[0] = (uint8_t)frames;
    for (unsigned n = 0; n < frames; n++) b[1 + n] = 10;
    for (long i = 0x100; i < *sz; i++) b[i] = (uint8_t)((i * 31u) ^ seed);
    return b;
}

static int try_provision(unsigned frames, uint8_t seed, bool print) {
    long sz; uint8_t *f = mkanim(frames, seed, &sz);
    last_err = NULL; err_at = 0;
    int rc = cmd_write(ANIM_BASE, f, sz, 1);
    bool hdr = anim_read_header();
    if (print) {
        printf("  %3u frames (%ld bytes, %ld sectors): %s", frames, sz, (sz + 4095) / 4096,
               rc ? "FAILED" : "ok, CRC verified");
        if (rc) printf(" (flash: %s at 0x%06X, after %u sectors erased = %u KB)", last_err, err_at, erased_ok, erased_ok * 4);
        printf("\n      then anim_read_header() -> %s, anim_count = %u; flash_unlocked = %d\n",
               hdr ? "true" : "false", anim_count, flash_unlocked);
    }
    free(f);
    flash_unlocked = false;   /* stands in for the reboot that clears it */
    return rc;
}

int main(void) {
    mem = malloc(CHIP_SIZE);
    memset(mem, 0xFF, CHIP_SIZE);
    int fails = 0;
    printf("ANIM_MAX = %u frames; an SPI byte %u us, a page program %u us, a round trip %u us\n", (unsigned)ANIM_MAX,
           BYTE_US, PROG_US, RTT_US);

    /* F-015 */
    printf("\nF-015: animations of 125, 131, 132 and ANIM_MAX frames, each over the last:\n");
    unsigned counts[] = {125u, 131u, 132u, (unsigned)ANIM_MAX};
    for (unsigned k = 0; k < 4; k++) {
        if (try_provision(counts[k], (uint8_t)(0x11 * (k + 1)), true)) fails++;
        else if (anim_count != counts[k]) { printf("  FAIL anim_count %u\n", anim_count); fails++; }
    }
    flash_set_unlocked(true);
    if (flash_writable(0x1A9000u, 4096u)) { printf("  FAIL the stock assets writable\n"); fails++; }
    if (flash_writable(FLASH_ASSET_BASE - 4096u, 8192u) == false) { /* the slot's end into the asset region: both sides allowed */ }
    flash_set_unlocked(false);
    if (flash_writable(0x540000u, 4096u)) { printf("  FAIL the slot writable while locked\n"); fails++; }

    /* F-044 */
    printf("\nF-044: 1,000 bytes in the asset region, the last page's program (%u us) longer than the round trip:\n", PROG_US);
    {
        uint8_t buf[1000];
        for (int i = 0; i < 1000; i++) buf[i] = (uint8_t)(i * 7 + 3);
        last_err = NULL;
        int rc = cmd_write(FLASH_ASSET_BASE + 0x200000u, buf, sizeof buf, 0);
        printf("  %s\n", rc ? last_err : "ok, CRC verified");
        if (rc) fails++;
    }

    /* F-001 */
    printf("\nF-001: the pass budget and the slice:\n");
    {
        uint8_t r[32] = {0x07, 0x11, FC_CRC32, 0x54, 0x00, 0x00, 0x01, 0x00, 0x00};   /* 64 KB at 0x540000 */
        sim_us += 100000u;          /* the chip idle */
        flash_channel_pass_end();
        uint64_t t0 = sim_us;
        flash_command(r, 32);
        uint64_t slice = sim_us - t0;
        uint32_t left0 = crc_left;
        printf("  the first slice: %u bytes in %llu us, reply %u\n", 65536u - left0, (unsigned long long)slice, r[3]);
        if (r[3] != FS_MORE || slice > CRC_SLICE_MS * 1000u + CRC_CHUNK * BYTE_US + 1000u) { printf("  FAIL the slice\n"); fails++; }
        int busy = 0;
        for (int n = 0; n < 1000; n++) {    /* a flood in the same pass */
            uint8_t q[32] = {0x07, 0x11, FC_CRC_NEXT};
            flash_command(q, 32);
            busy += q[3] == FS_BUSY;
        }
        printf("  1,000 more in the same pass: %d answered FS_BUSY, %u bytes folded\n", busy, left0 - crc_left);
        if (busy != 1000 || crc_left != left0) { printf("  FAIL the flood folded more\n"); fails++; }
        uint8_t e[32] = {0x07, 0x11, FC_ERASE, 0xD0, 0x00, 0x00};
        flash_command(e, 32);
        if (e[3] != FS_BUSY) { printf("  FAIL an erase in the same pass\n"); fails++; }
    }
    printf("  the longest single command over every write above: %llu us\n", (unsigned long long)worst_cmd_us);
    /* A page program is one SPI transaction (256 bytes, ~26 ms at this byte cost): it stays one command. */
    if (worst_cmd_us > 256u * BYTE_US + 2000u) { printf("  FAIL a command longer than a page program\n"); fails++; }

    printf("\nchip: %u erases, %u page programs, no stock-region write (the model aborts on one)\n", n_erases, n_programs);
    printf("RESULT: %s\n", fails ? "FAIL" : "PASS");
    free(mem);
    return fails ? 1 : 0;
}
