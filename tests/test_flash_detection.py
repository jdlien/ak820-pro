"""Exercise the macOS IORegistry parser with piped plist input (no USB access)."""
import pathlib
import plistlib
import subprocess
import sys
import unittest


class FlashDetectionTest(unittest.TestCase):
    def detect(self, tree, pid="0x7140"):
        script = (pathlib.Path(__file__).resolve().parents[1] / "flash.sh").read_text()
        parser = script.split('ioreg -a -l -p IOUSB | "$PY" -c \'', 1)[1].split("' \"$1\"", 1)[0]
        return subprocess.run([sys.executable, "-c", parser, pid],
                              input=plistlib.dumps(tree), capture_output=True)

    def test_nested_bootloader_with_no_hid_service(self):
        result = self.detect([{"IORegistryEntryChildren": [{"idVendor": 3141, "idProduct": 28992}]}])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_vid_and_pid_must_belong_to_same_device(self):
        result = self.detect([{"idVendor": 3141, "idProduct": 32777},
                              {"idVendor": 1, "idProduct": 28992}])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, b"")

    def test_running_firmware_and_absent_device(self):
        self.assertEqual(self.detect([{"idVendor": 3141, "idProduct": 32777}], "0x8009").returncode, 0)
        self.assertEqual(self.detect([]).returncode, 1)


if __name__ == "__main__":
    unittest.main()
