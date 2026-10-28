/* Host test of rtc.c's PCF write bookkeeping (rtc/rtc_pcf_sync.h): codex's
 * wireless-clock review, must-fixes 4 and 5. Build and run:
 *
 *   gcc -std=c11 -Wall -Wextra -I qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro/rtc \
 *       scripts/rtc_pcf_sync_test.c -o pst && ./pst
 *
 * (On Windows, mingw64's gcc first on PATH: CLAUDE.md.) */
#include <stdio.h>
#include "rtc_pcf_sync.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

int main(void) {
    /* A request, a run, a verify: done, not stale. */
    pcf_sync_t s = {0};
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);
    CHECK(s.pending && s.stale);
    pcf_sync_run_start(&s);
    CHECK(!pcf_sync_run_ok(&s));
    CHECK(!s.pending && !s.stale);

    /* Must-fix 4: a newer request during an older run survives its verify. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);            /* the wireless sync */
    pcf_sync_run_start(&s);          /* its write planned */
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);            /* USB corrects meanwhile */
    CHECK(pcf_sync_run_ok(&s));      /* the older write verifies: still pending */
    CHECK(s.pending && s.stale);
    pcf_sync_run_start(&s);          /* the newer one runs */
    CHECK(!pcf_sync_run_ok(&s));
    CHECK(!s.pending && !s.stale);

    /* The rtc fixes' review, must-fix 1: a request during a run marks it
     * superseded (the writer re-plans before writing), and re-starting the
     * run clears that. */
    s = (pcf_sync_t){0};
    pcf_sync_request(&s);
    pcf_sync_run_start(&s);
    CHECK(!pcf_sync_superseded(&s));
    pcf_sync_request(&s);            /* a legacy set mid-run */
    CHECK(pcf_sync_superseded(&s));
    pcf_sync_run_start(&s);          /* the writer re-plans */
    CHECK(!pcf_sync_superseded(&s));
    CHECK(!pcf_sync_run_ok(&s));

    /* Must-fix 5: a give-up is not pending (the board may sleep) but stays
     * stale, and is asked for again after the retry delay, not before. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);
    pcf_sync_run_start(&s);
    pcf_sync_gave_up(&s, 1000);
    CHECK(!s.pending && s.stale);
    CHECK(!pcf_sync_retry_due(&s, 1000));
    CHECK(!pcf_sync_retry_due(&s, 1000 + PCF_SYNC_RETRY_S - 1));
    CHECK(pcf_sync_retry_due(&s, 1000 + PCF_SYNC_RETRY_S));
    pcf_sync_request(&s);
    CHECK(!pcf_sync_retry_due(&s, 5000));   /* pending again: not twice */
    pcf_sync_run_start(&s);
    pcf_sync_run_ok(&s);
    CHECK(!s.stale);
    CHECK(!pcf_sync_retry_due(&s, 99999));

    /* The retry clock wraps with rtc_seconds_count. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_gave_up(&s, 0xFFFFFFF0u);
    CHECK(!pcf_sync_retry_due(&s, 0xFFFFFFF0u + 10));
    CHECK(pcf_sync_retry_due(&s, 0xFFFFFFF0u + PCF_SYNC_RETRY_S));

    /* A synchronous write clears stale; an idle, fresh PCF is never due. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_written(&s);
    CHECK(!s.stale && !pcf_sync_retry_due(&s, 12345));

    /* The board's own request (not a host correction) never makes it stale. */
    s = (pcf_sync_t){0};
    pcf_sync_request(&s);
    pcf_sync_run_start(&s);
    pcf_sync_gave_up(&s, 10);
    CHECK(!s.stale && !pcf_sync_retry_due(&s, 1000));

    /* The verify's must-fix 1: the writer takes the newer generation only once
     * its re-plan holds it. Until then the run stays superseded, so the older
     * snapshot is never written and certified for it. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);
    pcf_sync_run_start(&s);
    pcf_sync_host_accepted(&s);
    pcf_sync_request(&s);            /* a newer correction mid-run */
    /* ps_plan() fails this pass: run_start is not called */
    CHECK(pcf_sync_superseded(&s));  /* the next pass re-plans, not writes */
    pcf_sync_run_start(&s);          /* the plan held */
    CHECK(!pcf_sync_superseded(&s));
    CHECK(!pcf_sync_run_ok(&s) && !s.stale);

    /* The verify's should-fix 1: a SKIP_PCF correction leaves the PCF no
     * reference (stale), asks for no write of its own, and supersedes a
     * running write so it re-plans. */
    s = (pcf_sync_t){0};
    pcf_sync_host_skipped(&s);
    CHECK(s.stale && !s.pending);
    CHECK(!pcf_sync_retry_due(&s, 99999));   /* never asked for unprompted */
    s = (pcf_sync_t){0};
    pcf_sync_request(&s);
    pcf_sync_run_start(&s);
    pcf_sync_host_skipped(&s);       /* mid-run */
    CHECK(pcf_sync_superseded(&s));
    CHECK(pcf_sync_run_ok(&s));      /* the older run certifies nothing */
    CHECK(s.stale);
    pcf_sync_run_start(&s);          /* re-planned from the corrected clock */
    CHECK(!pcf_sync_run_ok(&s) && !s.stale && !s.no_retry);
    /* A skip on top of an owed retry keeps the retry. */
    s = (pcf_sync_t){0};
    pcf_sync_host_accepted(&s);
    pcf_sync_gave_up(&s, 0);
    pcf_sync_host_skipped(&s);
    CHECK(pcf_sync_retry_due(&s, PCF_SYNC_RETRY_S));

    /* 10-27: on USB's rate the writer starts only where nobody watches the
     * LEDs: dark, or ten minutes without input. Lit and typing it waits, a
     * minute short too. */
    CHECK(!pcf_sync_may_start(true, false, 0));
    CHECK(!pcf_sync_may_start(true, false, 5u * 60000u));
    CHECK(!pcf_sync_may_start(true, false, PCF_SYNC_UNSEEN_IDLE_MS - 1u));
    CHECK(pcf_sync_may_start(true, false, PCF_SYNC_UNSEEN_IDLE_MS));
    CHECK(pcf_sync_may_start(true, false, 0xFFFFFFFFu));
    CHECK(pcf_sync_may_start(true, true, 0));            /* dark: at once, a key just pressed or not */
    /* Codex: off USB's rate (unplugged; on battery the PCF is read, by the
     * board's own discipline and across a sleep) it goes at once, lit and
     * typing. */
    CHECK(pcf_sync_may_start(false, false, 0));
    CHECK(pcf_sync_may_start(false, true, 0));
    CHECK(PCF_SYNC_UNSEEN_IDLE_MS == 10u * 60u * 1000u);

    printf(fails ?"%d FAILED\n" : "rtc_pcf_sync: all passed\n", fails);
    return fails != 0;
}
