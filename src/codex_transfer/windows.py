from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import winreg
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000
DRIVE_REMOVABLE = 2


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


def removable_drives() -> list[Path]:
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    result: list[Path] = []
    for index in range(26):
        if mask & (1 << index):
            root = f"{chr(65 + index)}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) == DRIVE_REMOVABLE:
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
    command = str(winget) if winget.is_file() else "winget.exe"
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
            if match:
                latest = match.group(1).strip()
                result["checked"] = True
                result["latestVersion"] = latest
                installed_value = installed.get("version")
                result["isLatest"] = (
                    str(installed_value).strip() == latest if installed_value else None
                )
                result["message"] = (
                    "Latest version installed"
                    if result["isLatest"] is True
                    else "A different/newer Store version may be available"
                )
            else:
                result["message"] = "Microsoft Store bereikbaar, versienummer niet leesbaar"
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
