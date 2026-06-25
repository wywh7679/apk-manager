import unittest

from src.apk_manager import parse_adb_devices


class ParseAdbDevicesTest(unittest.TestCase):
    def test_only_returns_authorized_devices(self):
        output = """List of devices attached
emulator-5554 device
R58M123 unauthorized
192.168.0.10:5555 offline
ABCDEF device product:sdk model:Pixel device:generic
"""

        self.assertEqual(parse_adb_devices(output), ["emulator-5554", "ABCDEF"])


if __name__ == "__main__":
    unittest.main()
