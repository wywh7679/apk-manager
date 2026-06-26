import unittest

from src.apk_manager import (
    auth_headers,
    format_size,
    is_known_device_name,
    parse_adb_devices,
    parse_adb_metadata,
    parse_remote_apks,
)


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


class RemoteApkFeedTest(unittest.TestCase):
    def test_parse_remote_apks_resolves_relative_urls_and_ignores_invalid_items(self):
        payload = {
            "apks": [
                {"name": "app-release.apk", "url": "app-release.apk", "size": 1048576},
                {"name": "notes.txt", "url": "notes.txt"},
                {"name": "missing-url.apk"},
            ]
        }

        apks = parse_remote_apks(payload, "https://example.com/apks/apk-feed.php")

        self.assertEqual(len(apks), 1)
        self.assertEqual(apks[0].name, "app-release.apk")
        self.assertEqual(apks[0].url, "https://example.com/apks/app-release.apk")
        self.assertEqual(apks[0].size, 1048576)

    def test_parse_remote_apks_requires_apks_array(self):
        with self.assertRaises(ValueError):
            parse_remote_apks({"items": []}, "https://example.com/apks/apk-feed.php")

    def test_auth_headers_include_bearer_and_custom_header(self):
        self.assertEqual(
            auth_headers("secret"),
            {"Authorization": "Bearer secret", "X-APK-Manager-Token": "secret"},
        )
        self.assertEqual(auth_headers(""), {})

    def test_format_size(self):
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1048576), "1.0 MB")


if __name__ == "__main__":
    unittest.main()
