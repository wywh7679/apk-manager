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

### Build troubleshooting

If the build fails with `PermissionError: [WinError 5] Access is denied` for `dist\APK Manager.exe`, Windows still has the previous executable locked. Close APK Manager if it is running, close any File Explorer preview/details panes showing the executable, and rerun `build_windows.bat`. The build script now checks for this locked-file condition before invoking PyInstaller and prints that guidance.

## Use the app

1. Connect an Android device with USB debugging enabled, or start an emulator.
2. Launch `APK Manager.exe`.
3. Click **Refresh devices** and select a device. Devices are shown with their Android device name or model when available, followed by the adb serial in parentheses.
4. Click **Browse...** and select an `.apk` file.
5. Click **Install local APK**.

The app shows install progress and the `adb install` output in the log panel. On Windows, ADB command windows are hidden in the background so they do not pop up over the application.

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


## OnSite Installer

The second tab, **OnSite Installer**, mirrors the legacy PowerShell install workflow. Copy `onsite_config.json.example` to `onsite_config.json` next to `APK Manager.exe`, then set:

- `onsite_apk`: the OnSite FMS+ APK to install.
- `launcher_apk`: the optional Launcher3 APK used by the non-Android 6.0.1 workflow.
- `install_logs_dir`: where OS, machine-id, and key files are written after install.

Select the Android device, enter the serial number, and click **Run OnSite Install**. The workflow records the Android OS version, applies the display/ACC/date-time settings from the PowerShell script, installs and initializes OnSite FMS+, pulls `kf.osu` and `id.osu`, and writes logs under the configured log directory.
