/* The flash provisioning channel (plans/AUDIT-2026-10-31.md; first written as
 * the audit's verify-046, for F-015):
 *   F-015  an animation of up to ANIM_MAX (243) frames provisions; 132-243
 *          failed at the last sector, after the old one was erased;
 *   F-044  a CRC straight after FC_WRITE_END waits for the last page program
 *          (here 3 ms, longer than the 2 ms round trip) instead of reading the
 *          busy chip, and FC_INFO waits for an erase (codex's review);
 *   F-001  one chip operation a main-loop pass (a flood of commands in one
 *          pass folds nothing more), and a CRC slice bounded by time;
 *   and ak820ctl's side, from codex's review of Batch 4: an unlock whose reply
 *   is lost is turned off anyway, a failed relock fails the run, and a foreign
 *   report (Windows hands every handle every input report) is never read as
 *   the flash channel's reply.
 *
 * Compiles, verbatim (run.sh extracts them at build time):
 *   graphics/lcd_bus.c  FLASH_CMD_READ, ANIM_BASE..ANIM_MAX, the flash write path
 *                       (FLASH_CMD_WREN .. flash_crc32_acc), anim_count and
 *                       anim_read_header()
 *   hid_protocol.c      the flash channel's enum, CRC state, the pass budget,
 *                       fw_* state, flash_flush_page() and flash_command()
 * against a 16 MB model of the PY25Q128HA with real erase (to 0xFF) and program
 * (AND, wrapping in its page) semantics, timed: each SPI byte BYTE_US, an erase
 * ERASE_US and a program PROG_US busy, a READ or JEDEC ID begun while busy
 * floating (0xFF). The host is ak820ctl.c itself (time-util-ak820pro, its
 * main() renamed), built against fake_hidapi/hidapi.h, whose device here runs
 * each report as a main-loop pass of its own after a host round trip (RTT_US),
 * with faults injected on the way back. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
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
static volatile bool blit_lost;   /* the display's repair flag: F-014's latch sets it */

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
        case FLASH_CMD_JEDEC: return read_while_busy ? 0xFF : i == 1 ? 0x85 : i == 2 ? 0x60 : 0x18;
        case FLASH_CMD_READ: case FLASH_CMD_PAGE_PROG: case FLASH_CMD_SEC_ERASE:
            if (i <= 3) { caddr = (caddr << 8) | b; return 0xFF; }
            if (ccmd == FLASH_CMD_READ) return read_while_busy ? 0xFF : mem[(caddr + i - 4) & (CHIP_SIZE - 1)];
            if (ccmd == FLASH_CMD_PAGE_PROG && i - 4 < 256) pg[i - 4] = b;
            return 0xFF;
    }
    return 0xFF;
}
static void spi1_xfer(uint8_t b) { (void)spi1_rw(b); }

/* ---- the device ak820ctl.c talks to (fake_hidapi/hidapi.h) ---------------- */
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>
#include "hidapi.h"
int ak820ctl_main(int argc, char **argv);

static uint64_t worst_cmd_us;   /* the longest one command took: a main-loop pass's share */
#define INQ 32                  /* the OS's input buffer (Windows' default count); full, it drops the oldest */
static uint8_t  inq[INQ][32];
static unsigned inq_head, inq_n;
static struct {
    int      drop_cmd, drop_arg;   /* lose the reply to the next such command (arg -1: any) */
    bool     foreign_before_busy;  /* a Windows text echo queued ahead of every FS_BUSY reply */
    unsigned dropped, foreign;
} fault;
static uint32_t info_taken = 0xFFFFFFFFu;   /* the last FC_INFO FS_OK reply ak820ctl read: its id */
static unsigned n_info_busy;

static void inq_push(const uint8_t *r) {
    if (inq_n == INQ) { inq_head = (inq_head + 1) % INQ; inq_n--; }
    memcpy(inq[(inq_head + inq_n++) % INQ], r, 32);
}
int hid_init(void) { return 0; }
int hid_exit(void) { return 0; }
static struct hid_device_info the_dev = {"fake", 0x0C45, 0x8009, 0xFF60, 0x61, 1, NULL};
struct hid_device_info *hid_enumerate(unsigned short v, unsigned short p) { (void)v; (void)p; return &the_dev; }
void hid_free_enumeration(struct hid_device_info *d) { (void)d; }
hid_device *hid_open_path(const char *path) { (void)path; inq_n = 0; return (hid_device *)&the_dev; }
const wchar_t *hid_error(hid_device *d) { (void)d; return L"fake"; }
void hid_close(hid_device *d) { (void)d; }
int hid_write(hid_device *d, const unsigned char *data, size_t len) {
    (void)d;
    if (len != 33) { fprintf(stderr, "hid_write of %zu bytes\n", len); abort(); }
    uint8_t rep[32];
    memcpy(rep, data + 1, 32);
    sim_us += RTT_US;                    /* the host's round trip */
    flash_channel_pass_end();            /* a main-loop pass of its own */
    uint64_t t0 = sim_us;
    flash_command(rep, 32);              /* raw_hid_receive -> is_flash_cmd -> flash_command */
    uint64_t dt = sim_us - t0;
    if (dt > worst_cmd_us) worst_cmd_us = dt;
    if (rep[2] == FC_INFO && rep[3] == FS_BUSY) n_info_busy++;
    if (fault.drop_cmd >= 0 && rep[2] == fault.drop_cmd && (fault.drop_arg < 0 || data[1 + 3] == fault.drop_arg)) {
        fault.drop_cmd = -1;
        fault.dropped++;
        return 33;                       /* the command ran; its reply is lost */
    }
    if (fault.foreign_before_busy && rep[3] == FS_BUSY) {
        static const uint8_t echo[32] = {0x07, 0x12, 0x03, 0x00, 'n', 'o', 'w', ' ', 'p', 'l', 'a', 'y'};
        inq_push(echo);                  /* another agent's line-0 text echo */
        fault.foreign++;
    }
    inq_push(rep);
    return 33;
}
int hid_read_timeout(hid_device *d, unsigned char *out, size_t len, int ms) {
    (void)d;
    if (!inq_n) { sim_us += (uint64_t)ms * 1000u; return 0; }
    uint8_t *r = inq[inq_head];
    inq_head = (inq_head + 1) % INQ; inq_n--;
    memcpy(out, r, len < 32 ? len : 32);
    if (r[0] == 0x07 && r[1] == 0x11 && r[2] == FC_INFO && r[3] == FS_OK)
        info_taken = ((uint32_t)r[4] << 16) | ((uint32_t)r[5] << 8) | r[6];
    return 32;
}

/* One ak820ctl run, its output kept in the log unless it fails unexpectedly. */
static const char *tmpdir;
static int ctl(int n, ...) {   /* n: the arguments after argv[0] */
    char *argv[8] = {"ak820ctl"};
    int   argc    = n + 1;
    va_list ap; va_start(ap, n);
    for (int i = 1; i < argc; i++) argv[i] = va_arg(ap, char *);
    va_end(ap);
    char log[512]; snprintf(log, sizeof log, "%s/ak820ctl.log", tmpdir);
    fflush(stdout); fflush(stderr);
    int so = dup(1), se = dup(2), fd = open(log, O_WRONLY | O_CREAT | O_APPEND, 0644);
    dup2(fd, 1); dup2(fd, 2); close(fd);
    int rc = ak820ctl_main(argc, argv);
    fflush(stdout); fflush(stderr);
    dup2(so, 1); dup2(se, 2); close(so); close(se);
    return rc;
}
static char *write_file(const char *name, const uint8_t *b, long sz) {
    static char path[4][512];
    static unsigned k;
    char *p = path[k++ % 4];
    snprintf(p, 512, "%s/%s", tmpdir, name);
    FILE *f = fopen(p, "wb");
    if (!f || fwrite(b, 1, (size_t)sz, f) != (size_t)sz) { perror(p); abort(); }
    fclose(f);
    return p;
}
static char *hex(uint32_t a) {
    static char s[4][16];
    static unsigned k;
    char *p = s[k++ % 4];
    snprintf(p, 16, "0x%06X", a);
    return p;
}
static uint32_t crc32_of(const uint8_t *p, size_t n) {
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) { c ^= p[i]; for (int b = 0; b < 8; b++) c = (c >> 1) ^ (0xEDB88320u & (-(int32_t)(c & 1))); }
    return ~c;
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
    uint32_t e0 = n_erases;
    int rc = ctl(5, "flash", "write", hex(ANIM_BASE), write_file("anim.bin", f, sz), "--unlock");
    bool hdr = anim_read_header();
    if (print) {
        printf("  %3u frames (%ld bytes, %ld sectors): %s, %u sectors erased\n", frames, sz, (sz + 4095) / 4096,
               rc ? "FAILED" : "ok, CRC verified", n_erases - e0);
        printf("      then anim_read_header() -> %s, anim_count = %u; flash_unlocked = %d\n",
               hdr ? "true" : "false", anim_count, flash_unlocked);
    }
    free(f);
    return rc;
}

static int fails;
#define CHECK(c, ...) do { if (c) { printf("  ok   "); } else { printf("  FAIL "); fails++; } printf(__VA_ARGS__); printf("\n"); } while (0)

int main(void) {
    tmpdir = getenv("TEST_TMP");
    if (!tmpdir) tmpdir = ".";
    fault.drop_cmd = -1;
    mem = malloc(CHIP_SIZE);
    memset(mem, 0xFF, CHIP_SIZE);
    printf("ANIM_MAX = %u frames; an SPI byte %u us, a page program %u us, a round trip %u us\n", (unsigned)ANIM_MAX,
           BYTE_US, PROG_US, RTT_US);

    /* F-015 */
    printf("\nF-015: animations of 125, 131, 132 and ANIM_MAX frames, each over the last, by ak820ctl flash write --unlock:\n");
    unsigned counts[] = {125u, 131u, 132u, (unsigned)ANIM_MAX};
    for (unsigned k = 0; k < 4; k++) {
        int rc = try_provision(counts[k], (uint8_t)(0x11 * (k + 1)), true);
        CHECK(rc == 0 && anim_count == counts[k] && !flash_unlocked, "%u frames provisioned, the unlock off after", counts[k]);
    }
    flash_set_unlocked(true);
    CHECK(!flash_writable(0x1A9000u, 4096u), "the stock assets never writable");
    flash_set_unlocked(false);
    CHECK(!flash_writable(0x540000u, 4096u), "the slot not writable while locked");

    /* F-044 */
    printf("\nF-044: 1,000 bytes in the asset region, the last page's program (%u us) longer than the round trip:\n", PROG_US);
    uint8_t small[1000];
    for (int i = 0; i < 1000; i++) small[i] = (uint8_t)(i * 7 + 3);
    CHECK(ctl(4, "flash", "write", hex(FLASH_ASSET_BASE + 0x200000u), write_file("small.bin", small, sizeof small)) == 0,
          "written and its CRC verified");
    printf("  ...and FC_INFO straight after an erase (50 ms busy):\n");
    CHECK(ctl(4, "flash", "erase", hex(0xE00000u), "1") == 0, "ak820ctl flash erase 0xE00000");
    n_info_busy = 0; info_taken = 0xFFFFFFFFu;
    CHECK(ctl(2, "info") == 0 && info_taken == 0x856018u,
          "ak820ctl info read the chip's id 0x856018 (got 0x%06X, after %u FS_BUSY), never the floating bus", info_taken, n_info_busy);

    /* ak820ctl's side (codex on Batch 4) */
    printf("\nak820ctl: the unlock(1) reached the board, its reply lost:\n");
    fault.drop_cmd = FC_UNLOCK; fault.drop_arg = 1;
    {
        long sz; uint8_t *f = mkanim(10, 0x5A, &sz);
        int rc = ctl(5, "flash", "write", hex(ANIM_BASE), write_file("anim.bin", f, sz), "--unlock");
        free(f);
        CHECK(fault.dropped == 1 && rc != 0, "the run failed (rc %d)", rc);
        CHECK(!flash_unlocked, "and turned the unlock off anyway (flash_unlocked = %d)", flash_unlocked);
    }
    fault.dropped = 0;
    printf("ak820ctl: the write verified, the relock's reply lost:\n");
    fault.drop_cmd = FC_UNLOCK; fault.drop_arg = 0;
    {
        long sz; uint8_t *f = mkanim(10, 0x6B, &sz);
        int rc = ctl(5, "flash", "write", hex(ANIM_BASE), write_file("anim.bin", f, sz), "--unlock");
        free(f);
        CHECK(fault.dropped == 1 && rc != 0, "the run fails, since the stock slots may still be writable (rc %d)", rc);
    }
    fault.dropped = 0;
    printf("ak820ctl: the same, from flash erase --unlock:\n");
    fault.drop_cmd = FC_UNLOCK; fault.drop_arg = 0;
    CHECK(ctl(5, "flash", "erase", hex(ANIM_BASE), "1", "--unlock") != 0 && fault.dropped == 1, "the erase run fails too");
    fault.dropped = 0;
    fault.drop_cmd = FC_UNLOCK; fault.drop_arg = 1;
    CHECK(ctl(5, "flash", "erase", hex(ANIM_BASE), "1", "--unlock") != 0 && !flash_unlocked,
          "and an erase whose unlock reply was lost turns the unlock off (flash_unlocked = %d)", flash_unlocked);
    fault.drop_cmd = -1; fault.dropped = 0;

    printf("ak820ctl: another agent's text echo (07 12 03 00 ...) queued ahead of every FS_BUSY reply:\n");
    {
        static uint8_t a[40960], b[40960];
        for (size_t i = 0; i < sizeof a; i++) { a[i] = (uint8_t)(i * 13 + 1); b[i] = (uint8_t)(i * 29 + 7); }
        uint32_t at = FLASH_ASSET_BASE + 0x300000u;
        CHECK(ctl(4, "flash", "write", hex(at), write_file("a.bin", a, sizeof a)) == 0, "the first contents written");
        fault.foreign_before_busy = true;
        int rc = ctl(4, "flash", "write", hex(at), write_file("b.bin", b, sizeof b));
        fault.foreign_before_busy = false;
        CHECK(fault.foreign > 0, "%u foreign reports came in during the second write", fault.foreign);
        CHECK(rc == 0 && crc32_of(mem + at, sizeof b) == crc32_of(b, sizeof b),
              "it was written and verified all the same, every sector erased (rc %d)", rc);
    }

    printf("ak820ctl: a second flash session while one holds the lock (codex's verify):\n");
    {
        char lk[512];
        snprintf(lk, sizeof lk, "%s/ak820ctl-flash.lock", tmpdir);
        setenv("AK820CTL_LOCK", lk, 1);
        int fd = open(lk, O_RDWR | O_CREAT, 0600), held = fd >= 0 && flock(fd, LOCK_EX | LOCK_NB) == 0;
        uint32_t e0 = n_erases;
        int rc = ctl(4, "flash", "write", hex(FLASH_ASSET_BASE + 0x200000u), write_file("small.bin", small, sizeof small));
        CHECK(held && rc != 0 && n_erases == e0, "refused, nothing erased (rc %d)", rc);
        if (fd >= 0) close(fd);
        CHECK(ctl(4, "flash", "write", hex(FLASH_ASSET_BASE + 0x200000u), write_file("small.bin", small, sizeof small)) == 0,
              "and runs once the other has ended");
        unsetenv("AK820CTL_LOCK");
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
        CHECK(r[3] == FS_MORE && slice <= CRC_SLICE_MS * 1000u + CRC_CHUNK * BYTE_US + 1000u, "the slice bounded by time");
        int busy = 0;
        for (int n = 0; n < 1000; n++) {    /* a flood in the same pass */
            uint8_t q[32] = {0x07, 0x11, FC_CRC_NEXT};
            flash_command(q, 32);
            busy += q[3] == FS_BUSY;
        }
        CHECK(busy == 1000 && crc_left == left0, "1,000 more in the same pass: %d answered FS_BUSY, %u bytes folded",
              busy, left0 - crc_left);
        uint8_t e[32] = {0x07, 0x11, FC_ERASE, 0xD0, 0x00, 0x00};
        flash_command(e, 32);
        CHECK(e[3] == FS_BUSY, "an erase in the same pass answers FS_BUSY");
    }
    /* A page program is one SPI transaction (256 bytes, ~26 ms at this byte cost): it stays one command. */
    CHECK(worst_cmd_us <= 256u * BYTE_US + 2000u, "the longest single command over every write above: %llu us",
          (unsigned long long)worst_cmd_us);

    printf("\nchip: %u erases, %u page programs, no stock-region write (the model aborts on one)\n", n_erases, n_programs);
    printf("RESULT: %s (%d failed)\n", fails ? "FAIL" : "PASS", fails);
    free(mem);
    return fails ? 1 : 0;
}
