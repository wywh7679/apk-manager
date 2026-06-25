"""Windows GUI for installing APK files on selected Android devices."""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ADB_COMMAND = "adb"


class ApkManagerApp(tk.Tk):
    """Desktop application that wraps adb device discovery and APK installs."""

    def __init__(self) -> None:
        super().__init__()
        self.title("APK Manager")
        self.geometry("760x520")
        self.minsize(680, 460)

        self.apk_path = tk.StringVar()
        self.selected_device = tk.StringVar()
        self.status_text = tk.StringVar(value="Ready")
        self.devices: list[str] = []
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
            textvariable=self.selected_device,
            state="readonly",
            values=self.devices,
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
        result = self._run_adb(["devices"])
        if result.returncode != 0:
            self._queue_log("Unable to list devices. Is adb installed and on PATH?\n")
            self._queue_log(result.stderr or result.stdout)
            self.after(0, self._update_devices, [])
            return

        devices = parse_adb_devices(result.stdout)
        self.after(0, self._update_devices, devices)

    def _update_devices(self, devices: list[str]) -> None:
        self.devices = devices
        self.device_combo.configure(values=self.devices)
        if devices:
            if self.selected_device.get() not in devices:
                self.selected_device.set(devices[0])
            self.status_text.set(f"Found {len(devices)} device(s)")
            self._queue_log(f"Found devices: {', '.join(devices)}\n")
        else:
            self.selected_device.set("")
            self.status_text.set("No authorized devices found")
            self._queue_log("No authorized devices found. Check USB debugging authorization.\n")
        self._set_busy(False)

    def install_apk(self) -> None:
        apk = Path(self.apk_path.get())
        device = self.selected_device.get()

        if not device:
            messagebox.showerror("No device selected", "Select an Android device first.")
            return
        if not apk.is_file() or apk.suffix.lower() != ".apk":
            messagebox.showerror("Invalid APK", "Select a valid .apk file first.")
            return

        self._set_busy(True, "Installing APK...")
        self._queue_log(f"Installing {apk} on {device}...\n")
        self._run_background(lambda: self._install_apk_worker(device, apk))

    def _install_apk_worker(self, device: str, apk: Path) -> None:
        result = self._run_adb(["-s", device, "install", "-r", str(apk)])
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

    def _run_adb(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [ADB_COMMAND, *args],
            capture_output=True,
            check=False,
            text=True,
        )

    def _run_background(self, target) -> None:  # type: ignore[no-untyped-def]
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


def parse_adb_devices(output: str) -> list[str]:
    """Return serials for devices in the adb 'device' state."""
    devices: list[str] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


if __name__ == "__main__":
    app = ApkManagerApp()
    app.mainloop()
