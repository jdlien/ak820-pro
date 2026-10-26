#!/usr/bin/env bash
# Flash the AK820 Pro, preserving the VIA keymap and the RGB lighting across
# the erase.
#
# Flashing erases the emulated EEPROM, so the VIA keymap goes with it. This
# dumps it first, flashes, then writes it back -- the manual step that used to
# follow every single flash.
#
# ⚠️ The LIGHTING is the same problem and went unnoticed far longer. Nothing
# restored it, so every flash silently reverted the LEDs to `rgb_matrix.default`
# in keyboard.json -- through all nine flashes of 2026-09-03 before anyone
# noticed. The advice since was "keep that default equal to your setup", which
# is a rule a human has to remember; this is the version the script does.
#
# Usage:
#   ./flash.sh [firmware.bin] [--no-backup] [--no-lighting] [--no-profiles] [--no-battlog] [--on-reserve]
#
# Defaults to $QMK_HOME/a_jazz_ak820pro_via.bin. A failed backup of the
# keymap, the lighting or the settings profiles refuses to flash: --no-backup
# skips them all (and their restores), --no-lighting only the lighting,
# --no-profiles only the profiles. Each backup prints its file's time and
# size, so "is this backup from just now?" reads off the output.
#
# The profiles (P5a, plans/SETTINGS-PROFILES-PLAN.md) carry the live settings
# too: the screen level, the clock format, the indicators, the battery
# readout, the power mode, and the lighting. Where both firmwares have
# HC_PROFILES, that live record is the one RGB restore, in place of
# ak820lighting.py's, so two snapshots never overwrite each other.
#
# ⚠️ That path is SHARED: `qmk compile` always writes it, so a concurrent build
# in another session silently replaces your binary. The timestamp is printed
# below for exactly this reason -- confirm it is YOUR build, not merely recent.
set -u
cd "$(dirname "$0")" || exit 1
source ./env.sh                          # must be sourced from the repo root

# `hid` lives in the venv only. env.sh puts the venv's bin on PATH, but pin it
# the way nowplaying-macos.sh does so this still works if PATH is not what we
# expect. $AK820_VENV, not a literal "venv": the directory name is
# platform-specific (see env.sh).
PY="${PY:-$AK820_VENV/bin/python}"
[ -x "$PY" ] || PY=python3

FW="" ; BACKUP=1 ; LIGHTS=1 ; PROFS=1 ; PROF_HAVE=0 ; DUMPLOG=1 ; RESERVE_OK=0
for a in "$@"; do
    case "$a" in
        --no-backup) BACKUP=0 ;;
        --no-lighting) LIGHTS=0 ;;
        --no-profiles) PROFS=0 ;;
        --no-battlog) DUMPLOG=0 ;;
        --on-reserve) RESERVE_OK=1 ;;
        -h|--help)   sed -n '2,28p' "$0"; exit 0 ;;
        *)           FW="$a" ;;
    esac
done
FW="${FW:-$QMK_HOME/a_jazz_ak820pro_via.bin}"
[ -f "$FW" ] || { echo "no such firmware: $FW"; exit 1; }

BOOTLOADER=0x7140
RUNNING=0x8009
# On macOS the Sonix bootloader can exist in IOUSB without an IOHID service:
# hidapi then reports nothing even though our libusb flasher can open it.
# Match VID and PID on the SAME registry node. Other platforms keep hidapi.
usb() {
    case "$(uname -s)" in
        Darwin)
            ioreg -a -l -p IOUSB | "$PY" -c '
import plistlib, sys
pid = int(sys.argv[1], 16)
def present(node):
    if isinstance(node, dict):
        if node.get("idVendor") == 0x0C45 and node.get("idProduct") == pid:
            return True
        return any(present(v) for v in node.values())
    return isinstance(node, list) and any(present(v) for v in node)
sys.exit(0 if present(plistlib.loads(sys.stdin.buffer.read())) else 1)
' "$1" 2>/dev/null
            ;;
        MINGW*|MSYS*|CYGWIN*)
            # ⚠️ NOT hidapi on Windows. This probe runs once a second for up to
            # ten minutes while waiting for Fn+Esc, and `hid_enumerate` OPENS
            # every HID device on the machine each time -- the repeated sweep
            # that twice wedged the APC UPS attached to this one
            # (`../jdrgb/docs/ups-wedge-incident.md`). Windows can answer from
            # the device tree instead: Get-PnpDevice reads properties and opens
            # nothing. The bootloader is an ordinary HID device here (no Zadig),
            # so it appears in the tree exactly as the running board does.
            powershell.exe -NoProfile -NonInteractive -Command "
                \$id = 'VID_0C45&PID_$(printf '%04X' "$1")'
                if (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
                        Where-Object { \$_.InstanceId -like \"*\$id*\" }) { exit 0 } else { exit 1 }" >/dev/null 2>&1
            ;;
        *) "$PY" -c 'import hid,sys; sys.exit(0 if hid.enumerate(0x0C45, int(sys.argv[1],16)) else 1)' "$1" 2>/dev/null ;;
    esac
}

# BSD stat (macOS) and GNU stat (MSYS2, Linux) share no flags, and they cannot
# be probed by trying one first: GNU's -f means --file-system, so it SUCCEEDS
# and prints block counts instead of failing through to the -c form. Branch on
# the platform instead. Both print "<when>  (<n> bytes)".
fstat() {
    case "$(uname -s)" in
        Darwin|*BSD*) stat -f '%Sm  (%z bytes)' "$1" 2>/dev/null ;;
        *)            stat -c '%y  (%s bytes)' "$1" 2>/dev/null ;;
    esac || echo '(unknown)'
}

echo "firmware : $FW"
echo "built    : $(fstat "$FW")  <- confirm this is your build"
echo

# qmk console claims the HID interface exclusively; a second instance spins in a
# retry loop and can make the board look broken. Clear it before we need raw HID.
pkill -f "qmk console" 2>/dev/null && echo "stopped a running qmk console"

# --- 1. back up the keymap while QMK is still running ----------------------
# ⚠️ Under MSYS2, $HOME is C:\msys64\home\<user>, which has no Documents: the
# backups belong in the Windows profile's, where the Windows-side tools look.
DOCS="$HOME/Documents"
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) [ -n "${USERPROFILE:-}" ] && DOCS="$(cygpath -u "$USERPROFILE")/Documents" ;;
esac
KEYMAP="${KEYMAP:-$DOCS/ak820pro-keymap.json}"
LIGHTING="${LIGHTING:-$DOCS/ak820pro-lighting.json}"
PROFILES="${PROFILES:-$DOCS/ak820pro-profiles.json}"
if [ "$BACKUP" = 1 ]; then
    if usb "$BOOTLOADER"; then
        # Already in the bootloader: QMK is gone, so there is nothing to read.
        # Fall back to the last backup rather than refusing -- but say how old it
        # is, because restoring a stale keymap silently is worse than not doing it.
        if [ -f "$KEYMAP" ]; then
            echo "== already in the bootloader -- cannot dump =="
            echo "   using existing backup from $(fstat "$KEYMAP")"
            echo "   (if you have changed the keymap since, Ctrl-C, leave the"
            echo "    bootloader by replugging, and re-run to capture it)"
            echo
        else
            echo "Already in the bootloader and no backup exists at:"
            echo "  $KEYMAP"
            echo "Replug to get back into QMK and re-run, or pass --no-backup."
            exit 1
        fi
    else
        echo "== backing up the VIA keymap =="
        if ! "$PY" hostagent/ak820keymap.py dump "$KEYMAP"; then
            echo
            echo "Backup FAILED -- not flashing."
            echo "  Raw HID needs QMK running and the USB cable; the slider position"
            echo "  does not matter (raw-HID replies go over USB in any mode, 4b86d95014)."
            echo "  Re-run with --no-backup to flash anyway and lose the keymap."
            exit 1
        fi
        echo "   saved: $KEYMAP  $(fstat "$KEYMAP")"
        echo
    fi

    # Lighting, same story as the keymap, and fatal the same way: a failed dump
    # used to warn and flash anyway, which put the LEDs back on keyboard.json's
    # default -- or, with an old file present, restored THAT (10-01: the 09-29
    # backup). --no-lighting is the deliberate way past it. In the bootloader
    # there is nothing to read and an existing backup is used as-is.
    if [ "$LIGHTS" = 1 ]; then
        if ! usb "$BOOTLOADER"; then
            echo "== backing up the RGB lighting =="
            if ! "$PY" hostagent/ak820lighting.py dump "$LIGHTING"; then
                echo
                echo "Lighting backup FAILED -- not flashing."
                echo "  Re-run with --no-lighting to flash anyway; the LEDs then come back"
                echo "  as keyboard.json's rgb_matrix.default."
                exit 1
            fi
            echo "   saved: $LIGHTING  $(fstat "$LIGHTING")"
            echo
        elif [ -f "$LIGHTING" ]; then
            echo "   lighting: using existing backup from $(fstat "$LIGHTING")"
            echo
        fi
    fi

    # The settings profiles and the live settings, fatal the same way where
    # the firmware has HC_PROFILES. A firmware from before P5a answers
    # unhandled (exit 2): then nothing is saved this run, an older file is
    # NOT used, and the lighting is restored the old way. --no-profiles is
    # the deliberate way past a failure.
    if [ "$PROFS" = 1 ]; then
        if ! usb "$BOOTLOADER"; then
            echo "== backing up the settings profiles and the live settings =="
            "$PY" hostagent/ak820profiles.py dump "$PROFILES"; rc=$?
            if [ "$rc" = 0 ]; then
                PROF_HAVE=1
                echo "   saved: $PROFILES  $(fstat "$PROFILES")"
            elif [ "$rc" = 2 ]; then
                echo "   (this firmware predates them: the lighting is restored the old way)"
            else
                echo
                echo "Profiles backup FAILED -- not flashing."
                echo "  Re-run with --no-profiles to flash anyway; the profiles, and the screen, clock,"
                echo "  indicator, readout and power settings, then come back as the firmware's defaults."
                exit 1
            fi
            echo
        elif [ -f "$PROFILES" ]; then
            PROF_HAVE=1
            echo "   profiles: using existing backup from $(fstat "$PROFILES")"
            echo
        fi
    fi
fi

# --- 1b. the battery log ----------------------------------------------------
# The board keeps its battery log in RAM, and a flash erases it. Dump it first,
# fatal like the backups: on 2026-10-11 a retry loop around this script flashed
# at 15:39 with no dump since 12:10, and lost that stretch of a drain test.
# --no-battlog is the deliberate way past it. Independent of --no-backup.
# Power first. In the BT and 2.4G positions the board runs from its pack and
# flashes over the data lines alone (BACKLOG.md, "USB connects with no 5 V").
# That is fine with charge to spare, but a pack that dies mid-write leaves the
# app half-erased: the ROM bootloader survives, yet the board looks dead until
# it has power and a reflash. So refuse on battery once the RGB cut has fired
# (the last ~5 h, the reserve). --on-reserve is the deliberate way past it.
if [ "$RESERVE_OK" = 0 ] && ! usb "$BOOTLOADER"; then
    st=$("$PY" hostagent/ak820battery.py 2>/dev/null || true)
    if grep -q "^supply *battery" <<<"$st" && grep -q "lights_cut" <<<"$st"; then
        echo "The board is on battery, in its reserve (the RGB cut has fired) -- not flashing."
        echo "  Give it USB power (plug in, or the bench relay on), or re-run with --on-reserve."
        exit 1
    fi
fi
BATTLOG_DIR="${BATTLOG_DIR:-$DOCS/ak820pro-battlogs}"
if [ "$DUMPLOG" = 1 ] && ! usb "$BOOTLOADER"; then
    mkdir -p "$BATTLOG_DIR"
    blog="$BATTLOG_DIR/log-$(date +%Y%m%d-%H%M%S)-preflash.csv"
    echo "== dumping the battery log =="
    if ! "$PY" hostagent/ak820battery.py log "$blog"; then
        echo
        echo "Battery log dump FAILED -- not flashing."
        echo "  Re-run with --no-battlog to flash anyway and lose the log."
        exit 1
    fi
    echo "   saved: $blog  $(fstat "$blog")"
    echo
fi

# --- 2. the bootloader -----------------------------------------------------
# A dev build jumps on request (build.sh dev, hostagent/ak820bootloader.py), so
# the flash needs no hands. Only after the backups above, and only from a board
# running QMK. Any other build answers "unhandled", and Fn+Esc is asked for.
if ! usb "$BOOTLOADER" && usb "$RUNNING"; then
    echo "== asking the firmware to jump to the bootloader =="
    if "$PY" hostagent/ak820bootloader.py; then
        for _ in $(seq 1 30); do usb "$BOOTLOADER" && break; sleep 0.5; done
    fi
fi
if ! usb "$BOOTLOADER"; then
    echo "== press Fn+Esc to enter the bootloader (waiting up to 10 min) =="
    for _ in $(seq 1 600); do usb "$BOOTLOADER" && break; sleep 1; done   # 10 min: no need to race it
fi
usb "$BOOTLOADER" || { echo "timed out waiting for the bootloader (0x7140)"; exit 1; }
echo "bootloader detected (0C45:7140)"

# --- 3. flash ---------------------------------------------------------------
# Detached on purpose: interrupting sonixflasher mid-write leaves the board
# erased, and an impatient timeout has done exactly that here before.
echo "== flashing =="
LOG="$(mktemp "${TMPDIR:-/tmp}/ak820flash.XXXXXX")"   # -t differs BSD vs GNU
nohup ./SonixFlasherC/sonixflasher --vidpid 0c45/7140 --file "$FW" > "$LOG" 2>&1 &
FPID=$!
wait $FPID
grep -qi "Flash Verification Checksum: OK" "$LOG" || {
    echo "FLASH DID NOT VERIFY -- full log:"; cat "$LOG"; exit 1; }
tail -3 "$LOG"

# --- 4. wait for QMK, then restore -----------------------------------------
echo
echo "== waiting for the board to come back =="
for _ in $(seq 1 45); do usb "$RUNNING" && break; sleep 1; done
usb "$RUNNING" || { echo "board did not re-enumerate as 0x8009"; exit 1; }
sleep 6                                  # let the HID interfaces settle

if [ "$BACKUP" = 1 ]; then
    echo "== restoring the VIA keymap =="
    for try in 1 2 3; do
        "$PY" hostagent/ak820keymap.py restore "$KEYMAP" && break
        [ "$try" = 3 ] && { echo "restore failed -- run it by hand once the board settles:";
                            echo "  $PY hostagent/ak820keymap.py restore"; exit 1; }
        sleep 4
    done

    # The profiles and the live settings next, and with them the one
    # authoritative RGB restore: the live record where the new firmware has
    # HC_PROFILES and this run has its backup. Otherwise, or if it fails,
    # ak820lighting.py's restore as before.
    LIGHT_DONE=0
    if [ "$PROF_HAVE" = 1 ]; then
        echo "== restoring the settings profiles and the live settings =="
        for try in 1 2 3; do
            "$PY" hostagent/ak820profiles.py restore "$PROFILES"; rc=$?
            [ "$rc" = 0 ] && { LIGHT_DONE=1; break; }
            [ "$rc" = 2 ] && { echo "   (the new firmware has no HC_PROFILES: the lighting the old way)"; break; }
            [ "$try" = 3 ] && {
                echo "  profiles restore failed -- run it by hand once the board settles:"
                echo "    $PY hostagent/ak820profiles.py restore"
            }
            sleep 4
        done
    fi

    # After the keymap, because the keymap is the one worth failing over. A
    # lighting restore that does not take leaves the LEDs on the firmware
    # default, which is visible and fixable by hand.
    [ "$LIGHTS" = 1 ] && [ "$LIGHT_DONE" = 0 ] && echo "== restoring the RGB lighting =="
    [ "$LIGHTS" = 1 ] && [ "$LIGHT_DONE" = 0 ] && for try in 1 2 3; do
        "$PY" hostagent/ak820lighting.py restore "$LIGHTING" && break
        [ "$try" = 3 ] && {
            echo "  lighting restore failed -- run it by hand once the board settles:"
            echo "    $PY hostagent/ak820lighting.py restore"
        }
        sleep 4
    done
fi

echo
"$PY" hostagent/ak820keymap.py show >/dev/null 2>&1
# ak820health, not `ak820ctl info`: ak820ctl enumerates HID, which Windows
# must never do; ak820health opens by a listed path there.
"$PY" hostagent/ak820health.py >/dev/null 2>&1 && echo "raw HID: OK -- board is healthy"

# A flash erased the persisted RTC trim and the board re-seeded the clock from
# the PCF at a random sub-second phase, so it wants a sync -- from ONE owner.
# The daemon syncs by itself when the board re-enumerates ("sync
# (enumerated)"), and an ak820ctl sync beside it is two clock transactions at
# once: one's reply can pair with the other's timestamps into a wrong offset
# with a plausible round trip (CLAUDE.md; BACKLOG.md, "flash.sh syncs the clock
# beside the daemon"). So defer to a daemon that owns the clock and is alive
# (its status file says `clock=this daemon` and was written in the last 2 min).
case "$(uname -s)" in
    Darwin)               STATUS="$HOME/Library/Application Support/ak820pro/ak820-agent.status" ;;
    MINGW*|MSYS*|CYGWIN*) STATUS="$(cygpath -u "${LOCALAPPDATA:-}" 2>/dev/null)/ak820pro/ak820-agent.status" ;;
    *)                    STATUS="" ;;
esac
daemon_owns_clock() {
    [ -n "$STATUS" ] && [ -f "$STATUS" ] && grep -qx "clock=this daemon" "$STATUS" &&
        "$PY" -c 'import os,sys,time; sys.exit(0 if time.time() - os.path.getmtime(sys.argv[1]) < 120 else 1)' "$STATUS"
}
if daemon_owns_clock; then
    echo "== clock: left to the daemon (it syncs on the board's return; see \`ak820 status\`) =="
else
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*)
            # ak820ctl enumerates HID: never on Windows. The daemon is the
            # clock owner there (`ak820 install --clock`).
            echo "== clock: NOT synced -- no running daemon owns it; \`ak820 install --clock\` makes one =="
            ;;
        *)
            echo "== syncing the clock =="
            ./time-util-ak820pro/ak820ctl clock || echo "clock sync failed -- run ./time-util-ak820pro/ak820ctl clock by hand"
            ;;
    esac
fi
echo "done."
