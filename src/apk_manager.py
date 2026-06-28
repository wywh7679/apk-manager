"""Windows GUI for installing APK files on selected Android devices."""

from __future__ import annotations

import json
import queue
import ssl
import subprocess
import sys
import tempfile
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
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


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
        self.apk_path = tk.StringVar()
        self.force_downgrade = tk.BooleanVar(value=False)
        self.selected_remote_apk_label = tk.StringVar()
        self.selected_device_label = tk.StringVar()
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
        self.rowconfigure(4, weight=1)

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

        local_apk_frame = ttk.LabelFrame(self, text="Local APK file")
        local_apk_frame.grid(row=1, column=0, sticky="ew", **padding)
        local_apk_frame.columnconfigure(0, weight=1)

        self.apk_entry = ttk.Entry(local_apk_frame, textvariable=self.apk_path)
        self.apk_entry.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)

        browse_button = ttk.Button(local_apk_frame, text="Browse...", command=self.browse_apk)
        browse_button.grid(row=0, column=1, padx=(6, 10), pady=10)

        remote_apk_frame = ttk.LabelFrame(self, text="Remote APK feed")
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

        action_frame = ttk.Frame(self)
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

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.grid(row=4, column=0, sticky="nsew", **padding)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        status_bar = ttk.Label(self, textvariable=self.status_text, anchor="w")
        status_bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))

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
