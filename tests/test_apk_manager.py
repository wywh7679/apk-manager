import unittest

from src.apk_manager import is_known_device_name, parse_adb_devices, parse_adb_metadata


class ParseAdbDevicesTest(unittest.TestCase):
    def test_only_returns_authorized_devices_with_metadata(self):
        output = """List of devices attached
emulator-5554 device product:sdk_gphone64 model:Pixel_10_Pro device:emu64a
R58M123 unauthorized
192.168.0.10:5555 offline
ABCDEF device product:oriole model:Pixel_6 device:oriole
"""

        self.assertEqual(
            parse_adb_devices(output),
            [
                (
                    "emulator-5554",
                    {
                        "product": "sdk_gphone64",
                        "model": "Pixel_10_Pro",
                        "device": "emu64a",
                    },
                ),
                ("ABCDEF", {"product": "oriole", "model": "Pixel_6", "device": "oriole"}),
            ],
        )

    def test_parse_adb_metadata_ignores_fields_without_separator(self):
        self.assertEqual(
            parse_adb_metadata(["model:Pixel_10_Pro", "transport_id:1", "extra"]),
            {"model": "Pixel_10_Pro", "transport_id": "1"},
        )


class DeviceNameTest(unittest.TestCase):
    def test_filters_empty_null_and_unknown_names(self):
        self.assertFalse(is_known_device_name(""))
        self.assertFalse(is_known_device_name("null"))
        self.assertFalse(is_known_device_name("unknown"))
        self.assertTrue(is_known_device_name("Chris' Pixel"))
        self.assertTrue(is_known_device_name("Pixel 10 Pro"))


if __name__ == "__main__":
    unittest.main()
