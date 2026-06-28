# APK Manager

A small Windows desktop utility for selecting an APK file and installing it on a selected Android device through `adb`.

## Build a Windows executable

1. Install Python 3.10+ on Windows.
2. Install Android Platform Tools and make sure `adb.exe` is on your `PATH`.
3. From this repository, run:

```bat
build_windows.bat
```

The executable will be created at `dist\APK Manager.exe`.

## Use the app

1. Connect an Android device with USB debugging enabled, or start an emulator.
2. Launch `APK Manager.exe`.
3. Click **Refresh devices** and select a device. Devices are shown with their Android device name or model when available, followed by the adb serial in parentheses.
4. Click **Browse...** and select an `.apk` file.
5. Click **Install APK**.

The app shows install progress and the `adb install` output in the log panel.

## Remote APK feed

The app can also populate a dropdown from a PHP JSON feed. When a user selects a remote APK, the app downloads that APK through the PHP script and installs the downloaded file.

1. Copy `server/apk-feed.php` to the same web-server folder that contains the `.apk` files.
2. Change `APK_MANAGER_TOKEN` in `server/apk-feed.php` to a private value.
3. Copy `apk_manager_config.json.example` to `apk_manager_config.json` next to `APK Manager.exe`.
4. Set `feed_url` to the deployed PHP URL and `auth_token` to the same token used by the PHP script.
5. Optional: set `allow_self_signed_certificates` to `true` only for internal HTTPS servers that use self-signed certificates.

The token is sent automatically by the app in request headers for both the JSON list and APK downloads, so users do not need to enter it in the GUI. Use HTTPS for the feed URL so the token and APK downloads are protected in transit. Accepting self-signed certificates disables normal certificate verification for the feed and APK download requests, so only enable it for trusted internal servers.


## Downgrade installs

To install an APK over an existing newer version on the device, select **Allow version downgrade (-d)** before installing. This adds adb's `-d` flag to the install command.
