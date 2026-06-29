"""Windows GUI for installing APK files on selected Android devices."""

from __future__ import annotations

import json
import queue
import ssl
import subprocess
import sys
import tempfile
import time
import threading
import tkinter as tk
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable
from urllib.parse import urlparse

ADB_COMMAND = "adb"
UNKNOWN_DEVICE_NAME = "Android device"
CONFIG_FILE_NAME = "apk_manager_config.json"
ONSITE_CONFIG_FILE_NAME = "onsite_config.json"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024

ONSITE_LEGACY_SETTINGS = [
    ["settings", "put", "secure", "location_providers_allowed", "gps,wifi,network"],
    ["settings", "--user", "0", "put", "global", "acc_shutdown_delay", "60"],
    ["settings", "--user", "0", "put", "global", "acc_sleep_delay", "20"],
    ["settings", "--user", "0", "put", "system", "screen_auto_brightness_adj", "1.0"],
    ["settings", "--user", "0", "put", "system", "screen_brightness", "255"],
    ["settings", "--user", "0", "put", "system", "screen_brightness_mode", "0"],
    ["settings", "--user", "0", "put", "system", "screen_off_timeout", "0"],
    ["settings", "--user", "0", "put", "system", "user_rotation", "1"],
    ["settings", "--user", "0", "put", "system", "accelerometer_rotation", "0"],
    ["settings", "put", "global", "auto_time", "1"],
    ["settings", "put", "global", "auto_time_zone", "1"],
]

ONSITE_MODERN_SETTINGS = [
    command
    for command in ONSITE_LEGACY_SETTINGS
    if "screen_auto_brightness_adj" not in command
] + [["settings", "put", "secure", "doze_enabled", "0"]]

ONSITE_APP_COMMANDS = [
    ["pm", "disable-user", "--user", "0", "com.android.dialer"],
    ["pm", "disable-user", "--user", "0", "org.codeaurora.snapcam"],
    ["pm", "disable-user", "--user", "0", "org.codeaurora.gallery"],
    ["pm", "disable-user", "--user", "0", "com.android.quicksearchbox"],
    ["pm", "disable-user", "--user", "0", "com.android.vending"],
    ["pm", "disable-user", "--user", "0", "com.android.mms"],
    ["pm", "disable-user", "--user", "0", "com.android.calendar"],
    ["pm", "disable-user", "--user", "0", "com.android.contacts"],
    ["pm", "disable-user", "--user", "0", "com.android.deskclock"],
    ["pm", "disable-user", "--user", "0", "com.android.music"],
    ["pm", "disable-user", "--user", "0", "com.android.calculator2"],
    ["pm", "disable-user", "--user", "0", "com.android.documentsui"],
    ["pm", "disable-user", "--user", "0", "com.android.browser"],
    ["pm", "disable-user", "--user", "0", "com.android.soundrecorder"],
    ["pm", "disable-user", "--user", "0", "com.qualcomm.wfd.client"],
    ["pm", "disable-user", "--user", "0", "com.android.email"],
    ["pm", "enable", "com.android.dialer"],
    ["pm", "enable", "com.android.mms"],
    ["pm", "enable", "com.android.phone"],
    ["pm", "enable", "com.android.email"],
    ["pm", "enable", "com.android.browser"],
]


@dataclass(frozen=True)
class AndroidDevice:
    """Display and install metadata for one authorized adb device."""

    serial: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.serial})"


@dataclass(frozen=True)
class RemoteApk:
    """Metadata for an APK returned by the remote PHP feed."""

    name: str
    url: str
    size: int | None = None
    modified: str | None = None

    @property
    def label(self) -> str:
        if self.size is None:
            return self.name
        return f"{self.name} ({format_size(self.size)})"


@dataclass(frozen=True)
class OnsiteConfig:
    """Configuration for the OnSite installer workflow."""

    onsite_apk: str = "com.ses.onsite-debug-1.0.130.apk"
    launcher_apk: str = "Launcher3.apk"
    install_logs_dir: str = "install_logs"


@dataclass(frozen=True)
class ApkFeedConfig:
    """Configuration used to request the remote APK feed."""

    feed_url: str = ""
    auth_token: str = ""
    allow_self_signed_certificates: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.feed_url.strip())


class ApkManagerApp(tk.Tk):
    """Desktop application that wraps adb device discovery and APK installs."""

    def __init__(self) -> None:
        super().__init__()
        self.title("APK Manager")
        self.geometry("820x640")
        self.minsize(720, 560)

        self.config = load_feed_config()
        self.onsite_config = load_onsite_config()
        self.apk_path = tk.StringVar()
        self.force_downgrade = tk.BooleanVar(value=False)
        self.selected_remote_apk_label = tk.StringVar()
        self.selected_device_label = tk.StringVar()
        self.selected_onsite_device_label = tk.StringVar()
        self.onsite_serial = tk.StringVar()
        self.status_text = tk.StringVar(value="Ready")
        self.devices: list[AndroidDevice] = []
        self.remote_apks: list[RemoteApk] = []
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_log_queue)
        self.refresh_devices()
        if self.config.enabled:
            self.refresh_remote_apks()
        else:
            self._queue_log(
                f"Remote APK feed disabled. Create {CONFIG_FILE_NAME} next to the executable to enable it.\n"
            )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.apk_installer_tab = ttk.Frame(self.notebook)
        self.onsite_installer_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.apk_installer_tab, text="APK Installer")
        self.notebook.add(self.onsite_installer_tab, text="OnSite Installer")

        self._build_apk_installer_tab(self.apk_installer_tab)
        self._build_onsite_installer_tab(self.onsite_installer_tab)

    def _build_apk_installer_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        padding = {"padx": 12, "pady": 8}

        device_frame = ttk.LabelFrame(parent, text="Android device")
        device_frame.grid(row=0, column=0, sticky="ew", **padding)
        device_frame.columnconfigure(0, weight=1)

        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.selected_device_label,
            state="readonly",
            values=[],
        )
        self.device_combo.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)

        self.refresh_button = ttk.Button(
            device_frame,
            text="Refresh devices",
            command=self.refresh_devices,
        )
        self.refresh_button.grid(row=0, column=1, padx=(6, 10), pady=10)

        local_apk_frame = ttk.LabelFrame(parent, text="Local APK file")
        local_apk_frame.grid(row=1, column=0, sticky="ew", **padding)
        local_apk_frame.columnconfigure(0, weight=1)

        self.apk_entry = ttk.Entry(local_apk_frame, textvariable=self.apk_path)
        self.apk_entry.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)

        browse_button = ttk.Button(local_apk_frame, text="Browse...", command=self.browse_apk)
        browse_button.grid(row=0, column=1, padx=(6, 10), pady=10)

        remote_apk_frame = ttk.LabelFrame(parent, text="Remote APK feed")
        remote_apk_frame.grid(row=2, column=0, sticky="ew", **padding)
        remote_apk_frame.columnconfigure(0, weight=1)

        self.remote_apk_combo = ttk.Combobox(
            remote_apk_frame,
            textvariable=self.selected_remote_apk_label,
            state="readonly",
            values=[],
        )
        self.remote_apk_combo.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)

        self.refresh_apks_button = ttk.Button(
            remote_apk_frame,
            text="Refresh APKs",
            command=self.refresh_remote_apks,
        )
        self.refresh_apks_button.grid(row=0, column=1, padx=(6, 10), pady=10)
        if not self.config.enabled:
            self.refresh_apks_button.configure(state="disabled")

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=3, column=0, sticky="ew", **padding)
        action_frame.columnconfigure(0, weight=1)

        self.install_local_button = ttk.Button(
            action_frame,
            text="Install local APK",
            command=self.install_local_apk,
        )
        self.install_local_button.grid(row=0, column=1, sticky="e", padx=(6, 0))

        self.install_remote_button = ttk.Button(
            action_frame,
            text="Download and install selected APK",
            command=self.install_remote_apk,
        )
        self.install_remote_button.grid(row=0, column=2, sticky="e", padx=(6, 0))

        self.force_downgrade_check = ttk.Checkbutton(
            action_frame,
            text="Allow version downgrade (-d)",
            variable=self.force_downgrade,
        )
        self.force_downgrade_check.grid(row=1, column=1, columnspan=2, sticky="e", pady=(8, 0))
        if not self.config.enabled:
            self.install_remote_button.configure(state="disabled")

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.grid(row=4, column=0, sticky="nsew", **padding)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        status_bar = ttk.Label(parent, textvariable=self.status_text, anchor="w")
        status_bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))

    def _build_onsite_installer_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        padding = {"padx": 12, "pady": 8}

        setup_frame = ttk.LabelFrame(parent, text="OnSite install setup")
        setup_frame.grid(row=0, column=0, sticky="ew", **padding)
        setup_frame.columnconfigure(1, weight=1)

        ttk.Label(setup_frame, text="Android device").grid(row=0, column=0, sticky="w", padx=(10, 6), pady=8)
        self.onsite_device_combo = ttk.Combobox(
            setup_frame,
            textvariable=self.selected_onsite_device_label,
            state="readonly",
            values=[],
        )
        self.onsite_device_combo.grid(row=0, column=1, sticky="ew", padx=(6, 6), pady=8)
        self.refresh_onsite_devices_button = ttk.Button(
            setup_frame,
            text="Refresh devices",
            command=self.refresh_devices,
        )
        self.refresh_onsite_devices_button.grid(row=0, column=2, padx=(6, 10), pady=8)

        ttk.Label(setup_frame, text="Serial #").grid(row=1, column=0, sticky="w", padx=(10, 6), pady=8)
        self.onsite_serial_entry = ttk.Entry(setup_frame, textvariable=self.onsite_serial)
        self.onsite_serial_entry.grid(row=1, column=1, sticky="ew", padx=(6, 10), pady=8)

        onsite_apk = resolve_config_path(self.onsite_config.onsite_apk)
        launcher_apk = resolve_config_path(self.onsite_config.launcher_apk)
        config_text = f"OnSite APK: {onsite_apk}\nLauncher APK: {launcher_apk}\nLogs: {resolve_config_path(self.onsite_config.install_logs_dir)}"
        ttk.Label(setup_frame, text=config_text, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=8
        )

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=1, column=0, sticky="ew", **padding)
        action_frame.columnconfigure(0, weight=1)
        self.run_onsite_button = ttk.Button(
            action_frame,
            text="Run OnSite Install",
            command=self.run_onsite_install,
        )
        self.run_onsite_button.grid(row=0, column=1, sticky="e")

        log_frame = ttk.LabelFrame(parent, text="OnSite log")
        log_frame.grid(row=2, column=0, sticky="nsew", **padding)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.onsite_log_text = tk.Text(log_frame, wrap="word", state="disabled", height=12)
        self.onsite_log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        onsite_scrollbar = ttk.Scrollbar(log_frame, command=self.onsite_log_text.yview)
        onsite_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.onsite_log_text.configure(yscrollcommand=onsite_scrollbar.set)

    def browse_apk(self) -> None:
        path = filedialog.askopenfilename(
            title="Select APK",
            filetypes=(("Android packages", "*.apk"), ("All files", "*.*")),
        )
        if path:
            self.apk_path.set(path)

    def refresh_devices(self) -> None:
        self._set_busy(True, "Refreshing devices...")
        self._run_background(self._refresh_devices_worker)

    def _refresh_devices_worker(self) -> None:
        result = self._run_adb(["devices", "-l"])
        if result.returncode != 0:
            self._queue_log("Unable to list devices. Is adb installed and on PATH?\n")
            self._queue_log(result.stderr or result.stdout)
            self.after(0, self._update_devices, [])
            return

        devices = [
            AndroidDevice(serial=serial, name=self._lookup_device_name(serial, metadata))
            for serial, metadata in parse_adb_devices(result.stdout)
        ]
        self.after(0, self._update_devices, devices)

    def _lookup_device_name(self, serial: str, metadata: dict[str, str]) -> str:
        device_name = self._read_device_value(
            serial,
            ["shell", "settings", "get", "global", "device_name"],
        )
        if is_known_device_name(device_name):
            return device_name

        model = self._read_device_value(serial, ["shell", "getprop", "ro.product.model"])
        if is_known_device_name(model):
            return model

        metadata_model = metadata.get("model", "").replace("_", " ").strip()
        if is_known_device_name(metadata_model):
            return metadata_model

        return UNKNOWN_DEVICE_NAME

    def _read_device_value(self, serial: str, args: list[str]) -> str:
        result = self._run_adb(["-s", serial, *args], timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def _update_devices(self, devices: list[AndroidDevice]) -> None:
        previously_selected = self.selected_device_label.get()
        self.devices = devices
        labels = [device.label for device in self.devices]
        self.device_combo.configure(values=labels)
        self.onsite_device_combo.configure(values=labels)
        previously_selected_onsite = self.selected_onsite_device_label.get()
        if devices:
            if previously_selected in labels:
                self.selected_device_label.set(previously_selected)
            else:
                self.selected_device_label.set(labels[0])
            if previously_selected_onsite in labels:
                self.selected_onsite_device_label.set(previously_selected_onsite)
            else:
                self.selected_onsite_device_label.set(labels[0])
            self.status_text.set(f"Found {len(devices)} device(s)")
            self._queue_log(f"Found devices: {', '.join(labels)}\n")
        else:
            self.selected_device_label.set("")
            self.selected_onsite_device_label.set("")
            self.status_text.set("No authorized devices found")
            self._queue_log("No authorized devices found. Check USB debugging authorization.\n")
        self._set_busy(False)

    def refresh_remote_apks(self) -> None:
        if not self.config.enabled:
            messagebox.showerror(
                "Remote APK feed disabled",
                f"Create {CONFIG_FILE_NAME} next to the executable with a feed_url first.",
            )
            return
        self._set_busy(True, "Refreshing remote APKs...")
        self._run_background(self._refresh_remote_apks_worker)

    def _refresh_remote_apks_worker(self) -> None:
        try:
            payload = fetch_json(
                self.config.feed_url,
                self.config.auth_token,
                self.config.allow_self_signed_certificates,
            )
            apks = parse_remote_apks(payload, self.config.feed_url)
        except (OSError, ValueError, urllib.error.URLError) as error:
            self._queue_log(f"Unable to load remote APK feed: {error}\n")
            self.after(0, self._update_remote_apks, [])
            return
        self.after(0, self._update_remote_apks, apks)

    def _update_remote_apks(self, apks: list[RemoteApk]) -> None:
        previously_selected = self.selected_remote_apk_label.get()
        self.remote_apks = apks
        labels = [apk.label for apk in self.remote_apks]
        self.remote_apk_combo.configure(values=labels)
        if apks:
            if previously_selected in labels:
                self.selected_remote_apk_label.set(previously_selected)
            else:
                self.selected_remote_apk_label.set(labels[0])
            self.status_text.set(f"Found {len(apks)} remote APK(s)")
            self._queue_log(f"Found remote APKs: {', '.join(labels)}\n")
        else:
            self.selected_remote_apk_label.set("")
            self.status_text.set("No remote APKs found")
            self._queue_log("No remote APKs found in feed.\n")
        self._set_busy(False)

    def install_local_apk(self) -> None:
        apk = Path(self.apk_path.get())
        device = self._selected_device()

        if not device:
            messagebox.showerror("No device selected", "Select an Android device first.")
            return
        if not apk.is_file() or apk.suffix.lower() != ".apk":
            messagebox.showerror("Invalid APK", "Select a valid .apk file first.")
            return

        self._set_busy(True, "Installing local APK...")
        self._queue_log(f"Installing {apk} on {device.label}...\n")
        self._run_background(lambda: self._install_apk_worker(device, apk, cleanup=False))

    def install_remote_apk(self) -> None:
        device = self._selected_device()
        remote_apk = self._selected_remote_apk()

        if not device:
            messagebox.showerror("No device selected", "Select an Android device first.")
            return
        if not remote_apk:
            messagebox.showerror("No APK selected", "Select an APK from the remote feed first.")
            return

        self._set_busy(True, "Downloading APK...")
        self._queue_log(f"Downloading {remote_apk.name} from {remote_apk.url}...\n")
        self._run_background(lambda: self._download_and_install_worker(device, remote_apk))

    def _download_and_install_worker(self, device: AndroidDevice, remote_apk: RemoteApk) -> None:
        temp_path: Path | None = None
        try:
            temp_path = download_apk(
                remote_apk,
                self.config.auth_token,
                self.config.allow_self_signed_certificates,
            )
            self._queue_log(f"Downloaded to {temp_path}\n")
            self.after(0, self.status_text.set, "Installing downloaded APK...")
            self._install_apk_worker(device, temp_path, cleanup=True)
        except (OSError, urllib.error.URLError) as error:
            self._queue_log(f"Download failed: {error}\n")
            if temp_path:
                temp_path.unlink(missing_ok=True)
            self.after(0, self._install_finished, False, "APK download failed")


    def run_onsite_install(self) -> None:
        device = self._selected_onsite_device()
        serial_number = self.onsite_serial.get().strip()
        onsite_apk = resolve_config_path(self.onsite_config.onsite_apk)

        if not device:
            messagebox.showerror("No device selected", "Select an Android device first.")
            return
        if not serial_number:
            messagebox.showerror("Missing serial #", "Enter the OnSite serial number first.")
            return
        if not onsite_apk.is_file() or onsite_apk.suffix.lower() != ".apk":
            messagebox.showerror(
                "Missing OnSite APK",
                f"Update {ONSITE_CONFIG_FILE_NAME}; APK not found: {onsite_apk}",
            )
            return

        self._set_onsite_busy(True, "Running OnSite install...")
        self._queue_onsite_log(f"Version to be installed: {onsite_apk.name}\n")
        self._run_background(lambda: self._onsite_install_worker(device, serial_number))

    def _selected_onsite_device(self) -> AndroidDevice | None:
        selected_label = self.selected_onsite_device_label.get()
        return next((device for device in self.devices if device.label == selected_label), None)

    def _onsite_install_worker(self, device: AndroidDevice, serial_number: str) -> None:
        onsite_apk = resolve_config_path(self.onsite_config.onsite_apk)
        launcher_apk = resolve_config_path(self.onsite_config.launcher_apk)
        logs_dir = resolve_config_path(self.onsite_config.install_logs_dir)
        logs_dir.mkdir(parents=True, exist_ok=True)

        android_version = self._onsite_adb_text(device, ["shell", "getprop", "ro.build.version.release"]).strip()
        if not android_version:
            self._queue_onsite_log(
                "Make sure the tablet is connected via USB to this computer and has USB debugging enabled then try again.\n"
            )
            self.after(0, self._onsite_install_finished, False, "Unable to read Android version")
            return

        write_text_file(logs_dir / f"{safe_log_name(serial_number)}.os.txt", android_version)
        self._queue_onsite_log(f"Android {android_version}\n")

        if android_version == "6.0.1":
            self._run_onsite_android_601(device, serial_number, onsite_apk, logs_dir)
        else:
            self._run_onsite_modern_android(device, serial_number, onsite_apk, launcher_apk, logs_dir)

        self._queue_onsite_log("Install finished.\n")
        self.after(0, self._onsite_install_finished, True, "OnSite install finished")

    def _run_onsite_android_601(
        self,
        device: AndroidDevice,
        serial_number: str,
        onsite_apk: Path,
        logs_dir: Path,
    ) -> None:
        self._queue_onsite_log("Installing Onsite FMS+\n")
        self._onsite_adb(device, ["shell", "pm", "uninstall", "com.ses.onsite"])
        self._onsite_adb(device, ["install", "-d", "-g", str(onsite_apk)])
        self._launch_onsite(device, serial_number)
        time.sleep(5)
        self._pull_onsite_logs(device, serial_number, logs_dir)
        self._apply_settings(device, legacy=True)

    def _run_onsite_modern_android(
        self,
        device: AndroidDevice,
        serial_number: str,
        onsite_apk: Path,
        launcher_apk: Path,
        logs_dir: Path,
    ) -> None:
        self._apply_settings(device, legacy=False)
        if launcher_apk.is_file():
            self._queue_onsite_log("Installing launcher3\n")
            self._onsite_adb(device, ["install", "-r", str(launcher_apk)])
        else:
            self._queue_onsite_log(f"Launcher APK not found, skipping: {launcher_apk}\n")

        self._queue_onsite_log("Disabling shortcuts and apps\n")
        for command in ONSITE_APP_COMMANDS:
            self._onsite_shell(device, command)

        self._queue_onsite_log("Checking for a prior version of Onsite FMS\n")
        packages = self._onsite_adb_text(device, ["shell", "pm", "list", "packages", "com.ses.onsite"])
        if "package:com.ses.onsite" in packages:
            self._queue_onsite_log("Removing prior version of Onsite FMS\n")
            self._onsite_adb(device, ["shell", "pm", "uninstall", "com.ses.onsite"])

        self._queue_onsite_log("Installing Onsite FMS+\n")
        self._onsite_adb(device, ["install", "-d", "-g", str(onsite_apk)])
        self._launch_onsite(device, serial_number)
        time.sleep(5)
        self._pull_onsite_logs(device, serial_number, logs_dir)

    def _apply_settings(self, device: AndroidDevice, legacy: bool) -> None:
        self._queue_onsite_log("Applying system settings (display, acc, date/time)\n")
        commands = ONSITE_LEGACY_SETTINGS if legacy else ONSITE_MODERN_SETTINGS
        for command in commands:
            self._onsite_shell(device, command)

    def _launch_onsite(self, device: AndroidDevice, serial_number: str) -> None:
        self._queue_onsite_log("Launching Onsite FMS+ to set software key\n")
        self._onsite_adb(
            device,
            [
                "shell",
                "am",
                "start",
                "-S",
                "-n",
                "com.ses.onsite/com.ses.onsite.ui.MainActivity",
                "--es",
                "com.ses.onsite.args",
                "initialize",
                "--es",
                "com.ses.onsite.args2",
                serial_number,
            ],
        )

    def _pull_onsite_logs(self, device: AndroidDevice, serial_number: str, logs_dir: Path) -> None:
        self._queue_onsite_log("Retrieving machine id, serial and software key\n")
        safe_serial = safe_log_name(serial_number)
        self._onsite_adb(device, ["pull", "/storage/self/primary/kf.osu", str(logs_dir / f"{safe_serial}.kf.txt")])
        self._onsite_adb(device, ["pull", "/storage/self/primary/id.osu", str(logs_dir / f"{safe_serial}.id.txt")])

    def _onsite_shell(self, device: AndroidDevice, command: list[str]) -> None:
        self._onsite_adb(device, ["shell", *command])

    def _onsite_adb_text(self, device: AndroidDevice, args: list[str]) -> str:
        result = self._onsite_adb(device, args)
        return (result.stdout or result.stderr or "").strip()

    def _onsite_adb(self, device: AndroidDevice, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = self._run_adb(["-s", device.serial, *args])
        self._queue_onsite_log(result.stdout)
        self._queue_onsite_log(result.stderr)
        return result

    def _onsite_install_finished(self, success: bool, status: str) -> None:
        self.status_text.set(status)
        self._set_onsite_busy(False)
        if success:
            messagebox.showinfo("OnSite install complete", status)
        else:
            messagebox.showerror("OnSite install failed", "See the OnSite log panel for details.")

    def _set_onsite_busy(self, busy: bool, status: str | None = None) -> None:
        state = "disabled" if busy else "normal"
        self.run_onsite_button.configure(state=state)
        self.refresh_onsite_devices_button.configure(state=state)
        self.onsite_serial_entry.configure(state=state)
        self.onsite_device_combo.configure(state=state if busy else "readonly")
        if status:
            self.status_text.set(status)

    def _queue_onsite_log(self, text: str) -> None:
        if not text:
            return
        self.after(0, self._append_onsite_log, text)

    def _append_onsite_log(self, text: str) -> None:
        self.onsite_log_text.configure(state="normal")
        self.onsite_log_text.insert("end", text)
        if not text.endswith("\n"):
            self.onsite_log_text.insert("end", "\n")
        self.onsite_log_text.see("end")
        self.onsite_log_text.configure(state="disabled")

    def _selected_device(self) -> AndroidDevice | None:
        selected_label = self.selected_device_label.get()
        return next((device for device in self.devices if device.label == selected_label), None)

    def _selected_remote_apk(self) -> RemoteApk | None:
        selected_label = self.selected_remote_apk_label.get()
        return next((apk for apk in self.remote_apks if apk.label == selected_label), None)

    def _install_apk_worker(self, device: AndroidDevice, apk: Path, cleanup: bool) -> None:
        install_args = build_install_args(device.serial, apk, self.force_downgrade.get())
        result = self._run_adb(install_args)
        self._queue_log(result.stdout)
        self._queue_log(result.stderr)
        if cleanup:
            apk.unlink(missing_ok=True)
        if result.returncode == 0:
            self.after(0, self._install_finished, True, "APK installed successfully")
        else:
            self.after(0, self._install_finished, False, "APK install failed")

    def _install_finished(self, success: bool, status: str) -> None:
        self.status_text.set(status)
        self._set_busy(False)
        if success:
            messagebox.showinfo("Install complete", status)
        else:
            messagebox.showerror("Install failed", "See the log panel for details.")

    def _run_adb(
        self,
        args: list[str],
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [ADB_COMMAND, *args],
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            return subprocess.CompletedProcess(
                args=[ADB_COMMAND, *args],
                returncode=1,
                stderr=str(error),
            )
        except subprocess.TimeoutExpired as error:
            return subprocess.CompletedProcess(
                args=[ADB_COMMAND, *args],
                returncode=1,
                stderr=str(error),
            )

    def _run_background(self, target: Callable[[], None]) -> None:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        state = "disabled" if busy else "normal"
        self.refresh_button.configure(state=state)
        self.install_local_button.configure(state=state)
        self.force_downgrade_check.configure(state=state)
        self.refresh_onsite_devices_button.configure(state=state)
        if self.config.enabled:
            self.refresh_apks_button.configure(state=state)
            self.install_remote_button.configure(state=state)
        if status:
            self.status_text.set(status)

    def _queue_log(self, text: str) -> None:
        if text:
            self.log_queue.put(text)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", text)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(100, self._drain_log_queue)


def app_base_dir() -> Path:
    """Return the directory containing the executable or development script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def load_feed_config() -> ApkFeedConfig:
    """Load optional remote APK feed settings from JSON next to the executable."""
    config_path = app_base_dir() / CONFIG_FILE_NAME
    if not config_path.is_file():
        return ApkFeedConfig()

    with config_path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)
    return ApkFeedConfig(
        feed_url=str(data.get("feed_url", "")).strip(),
        auth_token=str(data.get("auth_token", "")).strip(),
        allow_self_signed_certificates=parse_bool(
            data.get("allow_self_signed_certificates", False)
        ),
    )


def load_onsite_config() -> OnsiteConfig:
    """Load OnSite installer settings from JSON next to the executable."""
    config_path = app_base_dir() / ONSITE_CONFIG_FILE_NAME
    if not config_path.is_file():
        return OnsiteConfig()

    with config_path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)
    return OnsiteConfig(
        onsite_apk=str(data.get("onsite_apk", OnsiteConfig.onsite_apk)).strip(),
        launcher_apk=str(data.get("launcher_apk", OnsiteConfig.launcher_apk)).strip(),
        install_logs_dir=str(data.get("install_logs_dir", OnsiteConfig.install_logs_dir)).strip(),
    )


def resolve_config_path(value: str) -> Path:
    """Resolve config paths relative to the executable directory."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return app_base_dir() / path


def safe_log_name(value: str) -> str:
    """Return a filesystem-safe log filename stem."""
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in value).strip("._") or "unknown"


def write_text_file(path: Path, value: str) -> None:
    """Write text to a file, creating its parent directory first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def fetch_json(
    url: str,
    auth_token: str,
    allow_self_signed_certificates: bool = False,
) -> Any:
    """Fetch JSON from a URL, adding the transparent feed token when configured."""
    request = urllib.request.Request(url, headers=auth_headers(auth_token))
    with urllib.request.urlopen(
        request,
        timeout=20,
        context=ssl_context(allow_self_signed_certificates),
    ) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def ssl_context(allow_self_signed_certificates: bool) -> ssl.SSLContext | None:
    """Return an unverified SSL context only when explicitly configured."""
    if not allow_self_signed_certificates:
        return None
    return ssl._create_unverified_context()


def parse_bool(value: Any) -> bool:
    """Parse booleans from JSON values without making arbitrary strings truthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return False


def auth_headers(auth_token: str) -> dict[str, str]:
    """Return headers used by the app and PHP endpoint for transparent authorization."""
    if not auth_token:
        return {}
    return {"Authorization": f"Bearer {auth_token}", "X-APK-Manager-Token": auth_token}


def parse_remote_apks(payload: Any, feed_url: str) -> list[RemoteApk]:
    """Parse the PHP JSON payload into remote APK choices."""
    if not isinstance(payload, dict) or not isinstance(payload.get("apks"), list):
        raise ValueError("Feed response must be a JSON object with an apks array")

    apks: list[RemoteApk] = []
    for item in payload["apks"]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        if not name or not url or not name.lower().endswith(".apk"):
            continue
        apks.append(
            RemoteApk(
                name=name,
                url=resolve_feed_url(feed_url, url),
                size=parse_optional_int(item.get("size")),
                modified=parse_optional_str(item.get("modified")),
            )
        )
    return apks


def resolve_feed_url(feed_url: str, apk_url: str) -> str:
    """Resolve relative APK URLs against the PHP feed URL."""
    parsed = urlparse(apk_url)
    if parsed.scheme and parsed.netloc:
        return apk_url
    return urllib.request.urljoin(feed_url, apk_url)


def parse_optional_int(value: Any) -> int | None:
    """Parse optional integer JSON values."""
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_optional_str(value: Any) -> str | None:
    """Parse optional string JSON values."""
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def download_apk(
    remote_apk: RemoteApk,
    auth_token: str,
    allow_self_signed_certificates: bool = False,
) -> Path:
    """Download a remote APK to a temporary file and return its path."""
    safe_name = Path(remote_apk.name).name
    if not safe_name.lower().endswith(".apk"):
        safe_name = f"{safe_name}.apk"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"-{safe_name}")
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            request = urllib.request.Request(remote_apk.url, headers=auth_headers(auth_token))
            with urllib.request.urlopen(
                request,
                timeout=120,
                context=ssl_context(allow_self_signed_certificates),
            ) as response:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    temp_file.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def format_size(size: int) -> str:
    """Format a byte count for display in the APK dropdown."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def build_install_args(serial: str, apk: Path, force_downgrade: bool) -> list[str]:
    """Build adb install arguments, optionally allowing version downgrades."""
    install_args = ["-s", serial, "install", "-r"]
    if force_downgrade:
        install_args.append("-d")
    install_args.append(str(apk))
    return install_args


def parse_adb_devices(output: str) -> list[tuple[str, dict[str, str]]]:
    """Return serials and adb metadata for devices in the adb 'device' state."""
    devices: list[tuple[str, dict[str, str]]] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append((parts[0], parse_adb_metadata(parts[2:])))
    return devices


def parse_adb_metadata(fields: list[str]) -> dict[str, str]:
    """Parse key:value metadata emitted by 'adb devices -l'."""
    metadata: dict[str, str] = {}
    for field in fields:
        key, separator, value = field.partition(":")
        if separator:
            metadata[key] = value
    return metadata


def is_known_device_name(value: str) -> bool:
    """Return whether adb returned a usable human-readable device name."""
    normalized = value.strip()
    return bool(normalized and normalized.lower() not in {"null", "unknown"})


if __name__ == "__main__":
    app = ApkManagerApp()
    app.mainloop()
