/* A tour of the real menu on the host test's fake panel: every page's frame as
 * a PPM, for checking the mockup against (verify.js). Built with
 * menu_s0_test.c included whole (its main renamed):
 *
 *   D=qmk_firmware-ak820pro/keyboards/a_jazz/ak820pro; M=$D/menu
 *   gcc -std=c11 -DMENU_HOST_TEST -I $M -I scripts plans/menu-mockup/tour.c $M/panel_owner.c $M/menu_input.c \
 *       $M/menu_slots.c $M/menu_fixture.c $M/menu_ops.c $M/menu_text.c $M/menu.c $M/menu_edit.c $M/profiles.c \
 *       $D/graphics/batt_text.c $D/graphics/power_bulb.c -o /tmp/tour
 *   /tmp/tour plans/menu-mockup/frames             # Small; then: node plans/menu-mockup/verify.js
 *   /tmp/tour plans/menu-mockup/frames-large large # Large;     node plans/menu-mockup/verify.js 300 large
 *   /tmp/tour plans/menu-mockup/frames-regular regular # Regular; node plans/menu-mockup/verify.js 300 regular */
#define main menu_s0_main
#include "menu_s0_test.c"
#undef main


static const char *outdir;
static void shot(const char *name) {
    char n[64];
    snprintf(n, sizeof n, "%s.ppm", name);
    write_ppm(outdir, n);
}
static void go(int row) { int n = row - (int)sub5_cursor(); if (n) m_turn(n); }   /* a turn of 0 is no turn */

int main(int argc, char **argv) {
    outdir = argc > 1 ? argv[1] : ".";
    fw_reset();
    if (argc > 2 && !strcmp(argv[2], "large")) {   /* 10-28: the tour in Large */
        fk_font = ENV_FONT_LARGE;
        ts_face = MT_LARGE;
    }
    if (argc > 2 && !strcmp(argv[2], "regular")) {   /* 10-28: and in Terminus regular, its titles bold */
        fk_font = ENV_FONT_REGULAR;
        ts_face = MT_LARGE_R;
    }
    fk_power = 1; fk_clock = 0;
    fk_lcd = fk_lcd_saved = 52;
    fk_batt_view = BATT_VIEW_PERCENT;
    fk_bt_set(fk_link_of(0, ENV_LINK_CONNECTED), 0);

    op27(11, 0, 0); m_settle();
    shot("top-c0");
    m_turn(1); shot("top-c1");
    go(T_BOOT); shot("top-p2");

    go(T_LIGHT); m_click(); shot("lighting");
    m_turn(1); m_click(); shot("lighting-effect"); m_hold(); m_unflash();
    go(2); m_click(); shot("edit-range"); m_hold(); m_unflash();
    go(3); m_click(); shot("edit-hue"); m_hold(); m_unflash();
    m_hold();

    go(T_SCREEN); m_click(); shot("screen"); m_hold(); m_unflash();
    go(T_CONN); m_click(); shot("conn"); m_hold();
    go(T_POWER); m_click(); shot("power"); m_hold();
    go(T_IND); m_click(); shot("ind"); m_hold();
    go(T_CLOCK); m_click(); shot("clock"); m_hold();
    go(T_BATT); m_click(); shot("batt"); m_hold();

    go(T_PROF); m_click(); shot("prof-empty");
    m_click(); fk_prof_settle(); m_unflash();
    m_to_pnew(); m_click(); fk_prof_settle(); m_unflash();
    shot("prof-list");
    go(1); m_click(); shot("prof-page");
    go(3); m_click(); shot("prof-rename"); m_hold(); m_unflash();
    m_hold(); m_hold();

    go(T_BOOT); m_click(); shot("boot"); m_hold();
    go(T_FONT); m_click(); shot("font"); m_hold(); m_unflash();
    go(T_DEFS); m_click(); shot("defaults"); m_hold();
    go(T_DIAG); m_click(); shot("diag"); m_hold();
    go(T_HELP); m_click(); shot("help");
    go(1); m_click(); shot("help-menu"); m_hold();
    go(2); m_click(); shot("help-via"); m_hold();
    go(3); m_click(); shot("help-keys"); m_hold();
    go(4); m_click(); shot("help-tips"); m_hold();
    go(5); m_click(); shot("help-more"); m_turn(1); shot("help-more-qr"); m_hold();   /* P1d: More info's two screens */
    m_hold();
    go(T_DIAG); m_click(); m_click(); shot("about"); m_hold(); m_hold();   /* 10-28: System info, in Diagnostics */
    printf("%d check(s) failed along the way\n", fails);
    return 0;
}
