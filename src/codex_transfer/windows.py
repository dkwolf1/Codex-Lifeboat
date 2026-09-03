from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
BUS_TYPE_USB = 7
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3


def launched_from_compressed_folder(executable: Path | None = None) -> bool:
    """Return true for Windows Explorer's temporary run-from-ZIP extraction."""
    executable = (executable or Path(sys.executable)).resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=False)
    try:
        relative = executable.relative_to(temporary_root)
    except ValueError:
        return False
    return any(".zip." in part.lower() or part.lower().endswith(".zip") for part in relative.parts)


def _user_shell_folder(name: str, fallback: Path) -> Path:
    if os.name != "nt":
        return fallback
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return Path(os.path.expandvars(str(value))).resolve(strict=False)
    except OSError:
        return fallback


def documents_folder(profile: Path | None = None) -> Path:
    profile = (profile or Path.home()).resolve(strict=False)
    if profile == Path.home().resolve(strict=False):
        return _user_shell_folder("Personal", profile / "Documents")
    return profile / "Documents"


def desktop_folder(profile: Path | None = None) -> Path:
    profile = (profile or Path.home()).resolve(strict=False)
    if profile == Path.home().resolve(strict=False):
        return _user_shell_folder("Desktop", profile / "Desktop")
    return profile / "Desktop"


def downloads_folder(profile: Path | None = None) -> Path:
    profile = (profile or Path.home()).resolve(strict=False)
    if profile == Path.home().resolve(strict=False):
        return _user_shell_folder(
            "{374DE290-123F-4565-9164-39C4925E467B}", profile / "Downloads"
        )
    return profile / "Downloads"


def known_folders(profile: Path | None = None) -> dict[str, str]:
    """Return user-independent Windows locations used by portable manifests.

    Registry-backed paths are used for the current user so redirected and
    OneDrive folders are represented correctly. Synthetic profiles used by
    tests and offline restore planning receive conventional fallback paths.
    """

    profile = (profile or Path.home()).resolve(strict=False)
    current = profile == Path.home().resolve(strict=False)
    registry_names = {
        "documents": "Personal",
        "desktop": "Desktop",
        "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "pictures": "My Pictures",
        "music": "My Music",
        "videos": "My Video",
    }
    fallback_names = {
        "documents": "Documents",
        "desktop": "Desktop",
        "downloads": "Downloads",
        "pictures": "Pictures",
        "music": "Music",
        "videos": "Videos",
    }
    result: dict[str, str] = {}
    for key, fallback_name in fallback_names.items():
        fallback = profile / fallback_name
        value = _user_shell_folder(registry_names[key], fallback) if current else fallback
        result[key] = str(value.resolve(strict=False))
    return result


def lifeboat_data_folder(profile: Path | None = None) -> Path:
    """Return machine-local Lifeboat state without writing inside projects."""

    profile = (profile or Path.home()).resolve(strict=False)
    if profile == Path.home().resolve(strict=False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).resolve(strict=False) / "Codex Lifeboat"
    return profile / "AppData" / "Local" / "Codex Lifeboat"


def project_registry_path(profile: Path | None = None) -> Path:
    return lifeboat_data_folder(profile) / "project-registry.json"


def lineage_state_path(profile: Path | None = None) -> Path:
    return lifeboat_data_folder(profile) / "lineage-state.json"


def device_state_path(profile: Path | None = None) -> Path:
    return lifeboat_data_folder(profile) / "device.json"


def location_mapping_registry_path(profile: Path | None = None) -> Path:
    return lifeboat_data_folder(profile) / "location-mappings.json"


def recovery_points_folder(profile: Path | None = None) -> Path:
    """Return the single managed home for local restore recovery points."""

    return lifeboat_data_folder(profile) / "recovery-points"


def _is_usb_backed_drive(letter: str) -> bool:
    """Detect USB disks that Windows reports as fixed, such as external SSDs."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.DeviceIoControl.argtypes = (
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_void_p,
    )
    handle = kernel32.CreateFileW(
        f"\\\\.\\{letter}:",
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        return False
    try:
        query = (ctypes.c_ubyte * 8)()
        output = (ctypes.c_ubyte * 1024)()
        returned = ctypes.c_ulong()
        success = kernel32.DeviceIoControl(
            handle,
            IOCTL_STORAGE_QUERY_PROPERTY,
            ctypes.byref(query),
            ctypes.sizeof(query),
            ctypes.byref(output),
            ctypes.sizeof(output),
            ctypes.byref(returned),
            None,
        )
        if not success or returned.value < 33:
            return False
        removable_media = bool(output[10])
        bus_type = int.from_bytes(bytes(output[28:32]), "little")
        return removable_media or bus_type == BUS_TYPE_USB
    finally:
        kernel32.CloseHandle(handle)


def _include_as_usb_destination(drive_type: int, usb_backed: bool) -> bool:
    return drive_type == DRIVE_REMOVABLE or (
        drive_type == DRIVE_FIXED and usb_backed
    )


def removable_drives() -> list[Path]:
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    result: list[Path] = []
    for index in range(26):
        if mask & (1 << index):
            root = f"{chr(65 + index)}:\\"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
            usb_backed = (
                _is_usb_backed_drive(chr(65 + index))
                if drive_type == DRIVE_FIXED
                else False
            )
            if _include_as_usb_destination(drive_type, usb_backed):
                result.append(Path(root))
    return result


def run_hidden(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def installed_codex_version() -> dict[str, Any]:
    if os.name != "nt":
        return {"detected": False, "version": None, "message": "Windows only"}
    script = (
        "$p=Get-AppxPackage | Where-Object {$_.Name -match 'ChatGPT|OpenAI'} | "
        "Sort-Object Version -Descending | Select-Object -First 1 Name,Version,PackageFullName;"
        "if($p){$p|ConvertTo-Json -Compress}else{"
        "$q=Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -match '^(ChatGPT|codex)$' -and $_.Path -match 'OpenAI[.]Codex_([^_]+)_'} | Select-Object -First 1;"
        "if($q){$m=[regex]::Match($q.Path,'OpenAI[.]Codex_([^_]+)_');"
        "[pscustomobject]@{Name='OpenAI.Codex';Version=$m.Groups[1].Value;PackageFullName=(Split-Path (Split-Path $q.Path -Parent) -Parent)}|ConvertTo-Json -Compress}}"
    )
    try:
        completed = run_hidden(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ]
        )
        if completed.returncode == 0 and completed.stdout.strip():
            value = json.loads(completed.stdout.strip())
            return {
                "detected": True,
                "name": value.get("Name"),
                "version": str(value.get("Version")),
                "packageFullName": value.get("PackageFullName"),
            }
    except Exception as exc:
        return {"detected": False, "version": None, "message": str(exc)}
    return {
        "detected": False,
        "version": None,
        "message": "ChatGPT/Codex AppX package not found",
    }


def latest_version_check(installed: dict[str, Any]) -> dict[str, Any]:
    """Best-effort Microsoft Store check; never blocks backup or restore."""
    result: dict[str, Any] = {
        "checked": False,
        "online": False,
        "installedVersion": installed.get("version"),
        "latestVersion": None,
        "isLatest": None,
        "message": "Latest version could not be verified",
    }
    if os.name != "nt":
        return result
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "winget.exe"
    try:
        winget_available = winget.is_file()
    except OSError:
        # WindowsApps aliases can exist while their target is unavailable or
        # access is denied. Online version detection is best-effort and must
        # never block backup, restore, diagnostics, or the release self-test.
        winget_available = False
    command = str(winget) if winget_available else "winget.exe"
    try:
        completed = run_hidden(
            [
                command,
                "show",
                "--id",
                "9NT1R1C2HH7J",
                "--source",
                "msstore",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout=30,
        )
        text = completed.stdout + "\n" + completed.stderr
        if completed.returncode == 0:
            result["online"] = True
            match = re.search(r"(?im)^\s*(?:Version|Versie)\s*:\s*([^\s]+)", text)
            if match and re.fullmatch(r"\d+(?:\.\d+){1,3}", match.group(1).strip()):
                latest = match.group(1).strip()
                result["checked"] = True
                result["latestVersion"] = latest
                installed_value = installed.get("version")
                installed_match = re.fullmatch(
                    r"\d+(?:\.\d+){1,3}", str(installed_value).strip()
                )
                if installed_match:
                    installed_parts = tuple(map(int, str(installed_value).split(".")))
                    latest_parts = tuple(map(int, latest.split(".")))
                    width = max(len(installed_parts), len(latest_parts))
                    installed_parts += (0,) * (width - len(installed_parts))
                    latest_parts += (0,) * (width - len(latest_parts))
                    result["isLatest"] = installed_parts >= latest_parts
                    result["message"] = (
                        "Installed version is current"
                        if result["isLatest"] is True
                        else "A newer Microsoft Store version may be available"
                    )
                else:
                    result["message"] = "Installed version number is not comparable"
            else:
                result["message"] = (
                    "Microsoft Store did not provide a comparable version number; "
                    "continuing with the installed version"
                )
        else:
            result["message"] = "Offline of Microsoft Store-controle niet beschikbaar"
    except Exception as exc:
        result["message"] = f"Versiecontrole niet beschikbaar: {exc}"
    return result


def detect_backup_packages() -> list[Path]:
    packages: list[Path] = []
    for drive in removable_drives():
        try:
            patterns = (
                "manifest/package.json",
                "*/manifest/package.json",
                "*/*/manifest/package.json",
                "*/*/*/manifest/package.json",
            )
            for pattern in patterns:
                for manifest in drive.glob(pattern):
                    packages.append(manifest.parent.parent)
        except OSError:
            continue
    unique = {str(path.resolve(strict=False)).lower(): path for path in packages}
    return sorted(unique.values(), key=lambda path: path.stat().st_mtime, reverse=True)
