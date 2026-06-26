"""Windows GUI for installing APK files on selected Android devices."""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

ADB_COMMAND = "adb"
UNKNOWN_DEVICE_NAME = "Android device"


@dataclass(frozen=True)
class AndroidDevice:
    """Display and install metadata for one authorized adb device."""

    serial: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.serial})"


class ApkManagerApp(tk.Tk):
    """Desktop application that wraps adb device discovery and APK installs."""

    def __init__(self) -> None:
        super().__init__()
        self.title("APK Manager")
        self.geometry("760x520")
        self.minsize(680, 460)

        self.apk_path = tk.StringVar()
        self.selected_device_label = tk.StringVar()
        self.status_text = tk.StringVar(value="Ready")
        self.devices: list[AndroidDevice] = []
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_log_queue)
        self.refresh_devices()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        padding = {"padx": 12, "pady": 8}

        device_frame = ttk.LabelFrame(self, text="Android device")
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

        apk_frame = ttk.LabelFrame(self, text="APK file")
        apk_frame.grid(row=1, column=0, sticky="ew", **padding)
        apk_frame.columnconfigure(0, weight=1)

        self.apk_entry = ttk.Entry(apk_frame, textvariable=self.apk_path)
        self.apk_entry.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)

        browse_button = ttk.Button(apk_frame, text="Browse...", command=self.browse_apk)
        browse_button.grid(row=0, column=1, padx=(6, 10), pady=10)

        action_frame = ttk.Frame(self)
        action_frame.grid(row=2, column=0, sticky="ew", **padding)
        action_frame.columnconfigure(0, weight=1)

        self.install_button = ttk.Button(
            action_frame,
            text="Install APK",
            command=self.install_apk,
        )
        self.install_button.grid(row=0, column=1, sticky="e")

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.grid(row=3, column=0, sticky="nsew", **padding)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        status_bar = ttk.Label(self, textvariable=self.status_text, anchor="w")
        status_bar.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))

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
        if devices:
            if previously_selected in labels:
                self.selected_device_label.set(previously_selected)
            else:
                self.selected_device_label.set(labels[0])
            self.status_text.set(f"Found {len(devices)} device(s)")
            self._queue_log(f"Found devices: {', '.join(labels)}\n")
        else:
            self.selected_device_label.set("")
            self.status_text.set("No authorized devices found")
            self._queue_log("No authorized devices found. Check USB debugging authorization.\n")
        self._set_busy(False)

    def install_apk(self) -> None:
        apk = Path(self.apk_path.get())
        device = self._selected_device()

        if not device:
            messagebox.showerror("No device selected", "Select an Android device first.")
            return
        if not apk.is_file() or apk.suffix.lower() != ".apk":
            messagebox.showerror("Invalid APK", "Select a valid .apk file first.")
            return

        self._set_busy(True, "Installing APK...")
        self._queue_log(f"Installing {apk} on {device.label}...\n")
        self._run_background(lambda: self._install_apk_worker(device, apk))

    def _selected_device(self) -> AndroidDevice | None:
        selected_label = self.selected_device_label.get()
        return next((device for device in self.devices if device.label == selected_label), None)

    def _install_apk_worker(self, device: AndroidDevice, apk: Path) -> None:
        result = self._run_adb(["-s", device.serial, "install", "-r", str(apk)])
        self._queue_log(result.stdout)
        self._queue_log(result.stderr)
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
            messagebox.showerror("Install failed", "See the log panel for adb output.")

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
        self.install_button.configure(state=state)
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
