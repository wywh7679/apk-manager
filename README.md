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
3. Click **Refresh devices** and select a device.
4. Click **Browse...** and select an `.apk` file.
5. Click **Install APK**.

The app shows install progress and the `adb install` output in the log panel.
