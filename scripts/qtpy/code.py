# The bench power logger (docs/test-bench.md): an INA228 in series on the
# AK820 pack's + lead and a MAX17048 across the pack, on the QT Py RP2040's
# STEMMA QT port. One line of raw integers per PERIOD_S over USB serial;
# scripts/power_log.py timestamps and converts them. Copy this and boot.py to
# CIRCUITPY.
#
#   H,<fields>   at start and every HEADER_S: what the D fields are and how
#                to scale them (repeated: the first comes behind the status
#                bar's escape codes, or before the Mac opens the port)
#   D,ms,vbus,vshunt,current,charge,temp,vcell,soc,crate
#   E,<where>,<error>
#
# The NeoPixel: dim green while the Mac has the serial port open and the
# INA228 answers; amber while no one reads it (the recorder stopped, or the
# Mac asleep), so rows are going nowhere; red while the INA228 does not answer.
#
# The INA228 is never reset here, so its charge register keeps counting across
# a restart of this script; it clears only when the QT Py loses power.
import time
import board
import digitalio
import neopixel_write
import supervisor

supervisor.runtime.autoreload = False  # a stray write to CIRCUITPY must not restart a run

PERIOD_S = 1.0
HEADER_S = 60.0
INA, MAX = 0x40, 0x36
R_SHUNT = 0.015      # Adafruit 5832's shunt (its driver's default)
CURRENT_LSB = 5e-6   # A per count: 2^19 counts = 2.62 A, the +-40.96 mV range at 15 mohm
SHUNT_CAL = round(13107.2e6 * CURRENT_LSB * R_SHUNT * 4)  # x4 for ADCRANGE=1

# GRB byte order. Green is the dimmest step there is, 1 of 255: visible on
# its own, and it does not light the desk; amber and red are warnings and
# stay brighter.
GREEN, AMBER, RED = bytes((1, 0, 0)), bytes((10, 30, 0)), bytes((0, 30, 0))
pixel_power = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
pixel_power.switch_to_output(value=True)
pixel = digitalio.DigitalInOut(board.NEOPIXEL)
pixel.switch_to_output()
shown = None


def show(colour):
    global shown
    if colour != shown:
        neopixel_write.neopixel_write(pixel, colour)
        shown = colour


i2c = board.STEMMA_I2C()
while not i2c.try_lock():
    pass


def wr16(addr, reg, val):
    i2c.writeto(addr, bytes([reg, val >> 8, val & 0xFF]))


def rd(addr, reg, n):
    b = bytearray(n)
    i2c.writeto_then_readfrom(addr, bytes([reg]), b)
    v = 0
    for x in b:
        v = (v << 8) | x
    return v


def signed(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def ina_init():
    dev = rd(INA, 0x3F, 2) >> 4
    if dev != 0x228:
        raise RuntimeError("device id 0x%x" % dev)
    wr16(INA, 0x00, 1 << 4)  # CONFIG: ADCRANGE=1 (+-40.96 mV); RST and RSTACC clear
    # ADC_CONFIG: continuous bus, shunt and die temperature, 1052 us each, 64
    # averages: a result every ~200 ms
    wr16(INA, 0x01, (0xF << 12) | (5 << 9) | (5 << 6) | (5 << 3) | 3)
    wr16(INA, 0x02, SHUNT_CAL)


def ina_read():
    vbus = rd(INA, 0x05, 3) >> 4                # 195.3125 uV per count
    vshunt = signed(rd(INA, 0x04, 3), 24) >> 4  # 78.125 nV per count at ADCRANGE=1
    current = signed(rd(INA, 0x07, 3), 24) >> 4  # CURRENT_LSB per count
    charge = signed(rd(INA, 0x0A, 5), 40)       # CURRENT_LSB coulombs per count
    temp = signed(rd(INA, 0x06, 2), 16)         # 7.8125 m degC per count: the board, not the cell
    return vbus, vshunt, current, charge, temp


def max_read():
    # The MAX17048 runs from the cell it measures: absent until a pack is on it,
    # and back at its defaults after any brown-out, so HIBRT is rewritten every
    # time (0 = never hibernate, so VCELL stays fresh, not every 45 s).
    wr16(MAX, 0x0A, 0x0000)
    vcell = rd(MAX, 0x02, 2)               # 78.125 uV per count
    soc = rd(MAX, 0x04, 2)                 # 1/256 % per count
    crate = signed(rd(MAX, 0x16, 2), 16)   # 0.208 %/h per count
    return vcell, soc, crate


HEADER = ("H,ms,vbus 195.3125uV,vshunt 78.125nV,current %gA,charge %gC,temp 7.8125mdegC,"
          "vcell 78.125uV,soc 1/256%%,crate 0.208%%/h,r_shunt %g,shunt_cal %d,period %g"
          % (CURRENT_LSB, CURRENT_LSB, R_SHUNT, SHUNT_CAL, PERIOD_S))
ina_ok = False
t_next = time.monotonic()
t_header = t_next
while True:
    if time.monotonic() >= t_header:
        print(HEADER)
        t_header += HEADER_S
    t_next += PERIOD_S
    ms = time.monotonic_ns() // 1000000
    ina = ("", "", "", "", "")
    mx = ("", "", "")
    try:
        if not ina_ok:
            ina_init()
            ina_ok = True
        ina = ina_read()
    except (OSError, RuntimeError) as e:
        ina_ok = False
        print("E,ina,%s" % e)
    try:
        mx = max_read()
    except OSError:
        pass
    print("D,%d,%s,%s,%s,%s,%s,%s,%s,%s" % ((ms,) + ina + mx))
    show(RED if not ina_ok else GREEN if supervisor.runtime.serial_connected else AMBER)
    d = t_next - time.monotonic()
    if d > 0:
        time.sleep(d)
    else:
        t_next = time.monotonic()
