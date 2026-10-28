"""The longest PCF transaction since boot (HC_RTC page 2's i2c_max_cycles, ILRC
cycles) and the I2C failures: how long the row ISR can be held off by a PCF
transfer. One read on the health channel; never enumerates HID."""
import sys

sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/scripts")
sys.path.insert(0, "C:/Users/jdlien/code/ak820-pro/hostagent")
from menu_s0_session import open_device  # noqa: E402
import ak820health as H  # noqa: E402

HC_RTC = 0x03
h = open_device()
try:
    b = H._txn_page(h, HC_RTC, 2)[4:]
    fails = b[2] | b[3] << 8
    deferred = b[4] | b[5] << 8
    cyc = b[6] | b[7] << 8 | b[8] << 16 | b[9] << 24
    print(f"i2c_max_cycles {cyc} (~{cyc / 33.4:.2f} ms at ~33.4 kHz ILRC), i2c_fail {fails}, deferred_passes {deferred}")
finally:
    h.close()
