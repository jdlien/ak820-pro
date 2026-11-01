# The key presser's board (scripts/presser/code.py; docs/test-bench.md, "The
# key presser"): serial only, never HID (or macOS opens its Keyboard Setup
# Assistant), a second serial port for the commands so the console's escape
# codes and REPL stay out of the data, and its own USB identity, pid.codes'
# test VID/PID for private use, so the bench's power recorder, which takes the
# first Adafruit board it finds, can never mistake it for the logger's QT Py.
# Runs at power-up and reset only. Copy this and code.py to the presser
# board's CIRCUITPY, NOT the power logger's.
import supervisor
import usb_cdc
import usb_hid
import usb_midi

usb_hid.disable()
usb_midi.disable()
usb_cdc.enable(console=True, data=True)
supervisor.set_usb_identification(manufacturer="ak820-pro bench", product="AK820 key presser",
                                  vid=0x1209, pid=0x0001)
