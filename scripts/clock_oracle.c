/* clock_oracle.c -- the pinned ak820ctl.c clock functions, run through the CRT
 * that builds ak820ctl.exe, so that ak820-agent's fixtures are the oracle's own
 * output rather than a reading of it.
 *
 * Every function below is copied verbatim from time-util-ak820pro/ak820ctl.c
 * at 7f92889f (cap_load, cap_save, board_sod, wrap_day, and the printf calls
 * of cmd_clock_read and cmd_clock). Do not "improve" them here; the point is
 * that they are the C.
 *
 * Build and run (Windows, the same mingw64 gcc that builds ak820ctl):
 *
 *     PATH="/c/msys64/mingw64/bin:$PATH" gcc -O2 -o clock_oracle scripts/clock_oracle.c
 *     ./clock_oracle                         # the cache and printf tables
 *     ./clock_oracle decode <32 hex bytes> <host_mid_sod> <rtt_ms>
 *
 * ⚠️ mingw64's bin must come FIRST on PATH or the xpack arm toolchain's DLLs
 * make gcc fail silently with no output (CLAUDE.md, "Building and flashing on
 * Windows"). It presents as `gcc rc=1` and nothing else.
 *
 * The tables feed ak820-agent/src/clock/cache.rs and transaction.rs; `decode`
 * feeds the phase-2 gate in ak820-agent/src/clock/mod.rs, where captured
 * replies from `ak820 clock --raw` must render identically in Rust.
 * `host_mid_sod` and `rtt_ms` are the values `--raw` prints, so the offset
 * line is computed from the same host instant both sides saw. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ---- cap_load / cap_save, verbatim, with the path parameterised ---------- */
typedef struct { int proto; double lead_ms; int b_ppm; int has_bias; } cap_t;
static const char *PATH = "clock_oracle.cap.tmp";
static cap_t cap_load(void) {
    cap_t c = { 0, 1.5, 0, 0 };
    FILE *f = fopen(PATH, "r");
    if (f) {
        int n = fscanf(f, "%d %lf %d", &c.proto, &c.lead_ms, &c.b_ppm);
        if (n < 2) { c.proto = 0; c.lead_ms = 1.5; }
        c.has_bias = (n == 3);
        fclose(f);
    }
    if (c.lead_ms < 0 || c.lead_ms > 10) c.lead_ms = 1.5;
    if (c.b_ppm < -600 || c.b_ppm > 600) c.has_bias = 0;
    return c;
}
static void cap_save(cap_t c) {
    FILE *f = fopen(PATH, "w");
    if (f) {
        if (c.has_bias) fprintf(f, "%d %.3f %d\n", c.proto, c.lead_ms, c.b_ppm);
        else            fprintf(f, "%d %.3f\n", c.proto, c.lead_ms);
        fclose(f);
    }
}

/* ---- board_sod / wrap_day, verbatim ------------------------------------- */
static double board_sod(const unsigned char *rep) {
    if (!rep[3]) return -1;
    unsigned cnt  = rep[12] | rep[13] << 8 | rep[14] << 16 | (unsigned)rep[15] << 24;
    unsigned per  = rep[16] | rep[17] << 8;
    unsigned pnom = rep[18] | rep[19] << 8;
    if (pnom == 0) pnom = per;
    double frac = 1.0 - ((double)per + 1.0 - (double)cnt) / ((double)pnom + 1.0);
    return rep[8] * 3600.0 + rep[9] * 60.0 + rep[10] + frac;
}
static double wrap_day(double d) { if (d > 43200) d -= 86400; if (d < -43200) d += 86400; return d; }

/* ---- the tables ---------------------------------------------------------- */
static void show(const char *content) {
    FILE *f = fopen(PATH, "w"); fputs(content, f); fclose(f);
    cap_t c = cap_load();
    printf("LOAD %-28s => proto=%d lead=%.17g b=%d has_bias=%d\n",
           content, c.proto, c.lead_ms, c.b_ppm, c.has_bias);
    cap_save(c);
    char buf[128] = {0}; f = fopen(PATH, "r"); if (fgets(buf, sizeof buf, f) == NULL) buf[0] = 0; fclose(f);
    printf("     resave                      => %s", buf);
}
static void save(int proto, double lead, int b, int has) {
    cap_t c = { proto, lead, b, has };
    cap_save(c);
    char buf[128] = {0}; FILE *f = fopen(PATH, "r"); if (fgets(buf, sizeof buf, f) == NULL) buf[0] = 0; fclose(f);
    printf("SAVE proto=%d lead=%.17g b=%d has=%d => %s", proto, lead, b, has, buf);
}
static int tables(void) {
    const char *files[] = {
        "", "\n", "2 2.354 -25\n", "2 1.5\n", "2\n", "abc\n", "2 abc\n",
        "2 12.0\n", "2 -0.5 10\n", "2 10\n", "2 0\n", "2 1.5 601\n", "2 1.5 -601\n",
        "2 1.5 -600\n", "2 1.5 600\n", "2 1.5 12.5\n", "2 1.5 5 extra\n",
        "0 1.5\n", "  2   2.354   -25  ", "2 nan\n", "2 inf\n", "2 -inf\n",
        "2 1e1\n", "2 1e-3 7\n", "3 4.5 7\n", "2 1.5 abc\n", "2 1.5 +25\n",
        "2\t2.5\t-25\n", "2 2.354 -25 garbage\n", "-1 1.5\n", "2 1.5 -0\n",
        "2 0x1p-1 7\n", "2 .5 7\n", "2 5. 7\n", "2 1.5 007\n", "2 1.5 0x10\n",
        "99999999999 1.5\n", "2 1.5 99999999999\n", "2 1e 7\n", "+ 1.5\n",
    };
    for (unsigned i = 0; i < sizeof files / sizeof *files; i++) show(files[i]);
    puts("");
    save(2, 2.354, -25, 1); save(2, 1.5, 0, 0); save(0, 1.5, 0, 0); save(2, 1.5, -25, 0);
    save(2, 0.0625, 0, 0); save(2, 1.2345, 0, 0); save(2, 10.0, 0, 0); save(2, 0.0, 0, 0);
    save(2, 2.3535, 0, 0); save(2, 0.0005, 0, 0); save(2, 1.0005, 0, 0); save(2, 9.9995, 0, 0);
    save(2, 0.0015, 0, 0); save(2, 0.0025, 0, 0); save(2, 2.0625, 0, 0); save(2, 0.5, 600, 1);
    save(2, 0.5, -600, 1); save(2, 3.14159265358979, 78, 1); save(2, 1.9995, 0, 0);
    save(2, 2.35449999999999981526, 0, 0); save(2, 2.3545000000000002593, 0, 0);
    puts("");
    /* %+.1f / %.1f / %.2f, which Python parses back */
    double v[] = { 0.0, -0.0, -0.04, -0.05, -0.06, 0.04, 0.05, 0.06, 0.15, 0.25, 0.35, 0.45,
                   2.5, 1.5, 60.0, 60.04, 60.05, 60.06, 400.0, 400.04, 400.05, 400.06,
                   -400.05, 999.95, 1042.5, 12.25, 12.35, -0.25, 0.125, 0.375, 3.0625, 13.0 };
    for (unsigned i = 0; i < sizeof v / sizeof *v; i++)
        printf("FMT %.17g => [%+.1f] [%.1f] [%.2f]\n", v[i], v[i], v[i], v[i]);
    double leads[] = { 2.354, 2.355, 2.345, 1.125, 1.135, 0.005, 0.015, 0.025, 10.0, 0.0, 2.854 };
    for (unsigned i = 0; i < sizeof leads / sizeof *leads; i++)
        printf("LEAD %.17g => [%.2f]\n", leads[i], leads[i]);
    puts("");
    /* the reported line and the warning, cmd_clock's printf calls verbatim */
    double best_off = -3.14159, after = 0.55, rtt_min = 4.9, U = 1.25, lead = 2.354;
    int good = 1, rc = 0, st = 1, has_bias = 1; double rtt2 = 0;
    printf("clock set (sub-second): before %+.1f ms, after %+.1f ms, rtt %.1f ms, U ~%.1f ms, lead now %.2f ms, bias %s%s\n",
           good ? best_off : 0.0, rc == 0 ? after : 0.0, rtt_min < 1e9 ? rtt_min : rtt2, U, lead,
           has_bias ? "sent" : "unknown", st == 1 ? " (slewing)" : "");
    after = 12.75;
    printf("warning: residual %+.1f ms exceeds 3U -- lead still calibrating, or a slew is in progress\n", after);
    remove(PATH);
    return 0;
}

/* ---- decode: cmd_clock_read's output for a captured reply --------------- */
static int decode(int argc, char **argv) {
    if (argc < 2 + 32 + 2) { fprintf(stderr, "usage: decode <32 hex bytes> <host_mid_sod> <rtt_ms>\n"); return 2; }
    unsigned char rep[32];
    for (int i = 0; i < 32; i++) rep[i] = (unsigned char)strtoul(argv[2 + i], NULL, 16);
    double host_mid = strtod(argv[2 + 32], NULL);
    double rtt      = strtod(argv[2 + 33], NULL);

    /* get_offset(), minus the transfer */
    int proto = rep[11];
    double b = board_sod(rep);
    int rc = b < 0 ? -2 : 0;
    double off = rc == 0 ? wrap_day(b - host_mid) * 1000.0 : 0;

    /* cmd_clock_read(), verbatim from the version check on */
    if (proto != 2) { printf("(legacy read: proto %d)\n", proto); return 1; }
    unsigned cnt = rep[12] | rep[13] << 8 | rep[14] << 16 | (unsigned)rep[15] << 24;
    unsigned per = rep[16] | rep[17] << 8, pnom = rep[18] | rep[19] << 8;
    {
        double frac = 1.0 - ((double)per + 1.0 - (double)cnt) / ((double)pnom + 1.0);
        printf("device %04d-%02d-%02d %02d:%02d:%02d%+.3f  (cnt %u / period %u, nominal %u)\n",
               2000 + rep[4], rep[5], rep[6], rep[8], rep[9], rep[10], frac, cnt, per, pnom);
    }
    if (rc == -2) { printf("device clock not set\n"); return 1; }
    printf("offset board-host %+.1f ms  rtt %.1f ms  flags 0x%02x  ref_state %u  sync_age %u min  last_host_offset %d ms\n",
           off, rtt, rep[20], rep[25], rep[26], (short)(rep[21] | rep[22] << 8));
    printf("sof_epoch %u  sof_frames_total %u  bias_in_use %d ppm\n", rep[27],
           rep[28] | rep[29] << 8 | rep[30] << 16 | (unsigned)rep[31] << 24, (short)(rep[23] | rep[24] << 8));
    return 0;
}

int main(int argc, char **argv) {
    if (argc > 1 && !strcmp(argv[1], "decode")) return decode(argc, argv);
    return tables();
}
