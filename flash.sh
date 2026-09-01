#!/usr/bin/env bash
# Flash the AK820 Pro, preserving the VIA keymap across the erase.
#
# Flashing erases the emulated EEPROM, so the VIA keymap goes with it. This
# dumps it first, flashes, then writes it back -- the manual step that used to
# follow every single flash.
#
# Usage:
#   ./flash.sh [firmware.bin] [--no-backup]
#
# Defaults to $QMK_HOME/a_jazz_ak820pro_via.bin.
#
# ⚠️ That path is SHARED: `qmk compile` always writes it, so a concurrent build
# in another session silently replaces your binary. The timestamp is printed
# below for exactly this reason -- confirm it is YOUR build, not merely recent.
set -u
cd "$(dirname "$0")" || exit 1
source ./env.sh                          # must be sourced from the repo root

# `hid` lives in the venv only. env.sh puts venv/bin on PATH, but pin it the way
# nowplaying-macos.sh does so this still works if PATH is not what we expect.
PY="${PY:-$AK820_ROOT/venv/bin/python}"
[ -x "$PY" ] || PY=python3

FW="" ; BACKUP=1
for a in "$@"; do
    case "$a" in
        --no-backup) BACKUP=0 ;;
        -h|--help)   sed -n '2,16p' "$0"; exit 0 ;;
        *)           FW="$a" ;;
    esac
done
FW="${FW:-$QMK_HOME/a_jazz_ak820pro_via.bin}"
[ -f "$FW" ] || { echo "no such firmware: $FW"; exit 1; }

BOOTLOADER='"idProduct" = 28992'         # 0x7140
RUNNING='"idProduct" = 32777'            # 0x8009
usb() { ioreg -p IOUSB -w0 -l 2>/dev/null | grep -q "$1"; }

echo "firmware : $FW"
stat -f "built    : %Sm  (%z bytes)  <- confirm this is your build" "$FW"
echo

# qmk console claims the HID interface exclusively; a second instance spins in a
# retry loop and can make the board look broken. Clear it before we need raw HID.
pkill -f "qmk console" 2>/dev/null && echo "stopped a running qmk console"

# --- 1. back up the keymap while QMK is still running ----------------------
KEYMAP="${KEYMAP:-$HOME/Documents/ak820pro-keymap.json}"
if [ "$BACKUP" = 1 ]; then
    if usb "$BOOTLOADER"; then
        # Already in the bootloader: QMK is gone, so there is nothing to read.
        # Fall back to the last backup rather than refusing -- but say how old it
        # is, because restoring a stale keymap silently is worse than not doing it.
        if [ -f "$KEYMAP" ]; then
            echo "== already in the bootloader -- cannot dump =="
            stat -f "   using existing backup from %Sm" "$KEYMAP"
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
            echo "  Raw HID needs QMK running and the dip switch on 'cable'."
            echo "  Re-run with --no-backup to flash anyway and lose the keymap."
            exit 1
        fi
        echo
    fi
fi

# --- 2. wait for the bootloader --------------------------------------------
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
LOG="$(mktemp -t ak820flash)"
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
fi

echo
"$PY" hostagent/ak820keymap.py show >/dev/null 2>&1
./time-util-ak820pro/ak820ctl info >/dev/null 2>&1 && echo "raw HID: OK -- board is healthy"
# A flash erased the persisted RTC trim and the board re-seeded the clock from
# the PCF at a random sub-second phase; set it properly now (clock-sync plan).
echo "== syncing the clock =="
./time-util-ak820pro/ak820ctl clock || echo "clock sync failed -- run ./time-util-ak820pro/ak820ctl clock by hand"
echo "done."
