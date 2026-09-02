#!/bin/bash
# Resync the AK820 Pro's RTC from host time. ONE-SHOT, run by hand.
#
# ⚠️ SUPERSEDED as a scheduled agent (2026-09-01). ak820-timekeeper.py does this
# every 5 min, on wake and on re-enumeration, with SOF-bias correction; its
# LaunchAgent replaced this one's, which was deliberately deleted. Do NOT
# schedule both: the raw-HID interface is exclusive, so the two would take turns
# failing. Kept because a manual one-shot sync is still occasionally useful.
#
# WHY THIS IS NEEDED: the SN32's internal RTC is disciplined to the on-board
# PCF8563, which is itself an uncompensated crystal running ~58 ppm fast on this
# unit -- about 5 s/day, measured over 24 h. The firmware's divider trim tracks
# the PCF perfectly; the PCF is simply wrong, so no firmware change helps. The
# only fix is a periodic resync from a machine that knows the real time.
#
# --no-wait because the firmware routes raw-HID REPLIES through the active host
# driver, so a round-trip command fails in BT/2.4G mode even with the cable in.
# A clock set needs no confirmation: if it silently misses, the next run fixes it.
#
# Requires the USB cable (the HID interface must exist); the dip switch position
# does not matter.
set -u
AK820_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CTL="${CTL:-$AK820_ROOT/time-util-ak820pro/ak820ctl}"
exec "$CTL" clock --no-wait
