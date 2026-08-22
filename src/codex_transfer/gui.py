from __future__ import annotations

import argparse
import json
import os
import queue
import tempfile
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import backup, restore, windows
from .validate import validate


TEXT = {
    "nl": {
        "title": "Codex Lifeboat",
        "subtitle": "Volledige Codex-back-up en 1-op-1 herstel voor Windows 10/11",
        "language": "Taal",
        "codex_home": "Gevonden Codex-map",
        "usb": "Gevonden USB-schijven",
        "backup": "1. Volledige back-up maken",
        "verify_backup": "2. Back-up controleren",
        "restore": "3. Volledig herstellen",
        "verify_restore": "4. Herstel controleren",
        "ready": "Gereed",
        "working": "Bezig… sluit dit venster niet.",
        "choose_destination": "Kies USB-schijf of doelmap voor de back-up",
        "choose_backup": "Kies de Codex-PortableBackup-map",
        "confirm_backup": "Codex moet volledig gesloten zijn. Een complete back-up van projecten, chats en instellingen maken naar:\n\n{path}?",
        "backup_done": "Back-up geslaagd:\n\n{path}",
        "valid_backup": "De back-up is volledig en geldig.\n\nThreads: {threads}\nProjecten: {projects}\nHashes: {hashes}",
        "invalid_backup": "De back-up is ongeldig:\n\n{errors}",
        "restore_intro": "Codex moet op deze computer geïnstalleerd, eenmaal geopend en aangemeld zijn. Sluit Codex volledig voordat u doorgaat.",
        "restore_confirm": "De veiligheidskopie is gemaakt:\n{safety}\n\nHuidige chats: {threads}\nHuidige projecten: {projects}\n\nWilt u de lokale Codex-inhoud vervangen door de 1-op-1 back-up?",
        "restore_cancelled": "Herstel geannuleerd. De veiligheidskopie is bewaard.",
        "restore_done": "Herstel en eindcontrole zijn geslaagd.\n\nVeiligheidskopie:\n{safety}",
        "valid_restore": "Het herstel is geldig.\n\nThreads: {threads}\nProjecten: {projects}",
        "error": "Fout",
        "warning": "Waarschuwing",
        "version_warning": "Versiecontrole: {message}\n\nGeïnstalleerd: {installed}\nOnline gevonden: {latest}\n\nWilt u toch doorgaan?",
        "no_usb": "Geen verwisselbare USB-schijf automatisch gevonden; kies handmatig een map.",
        "detected_backup": "Back-up automatisch gevonden:\n\n{path}\n\nDeze gebruiken?",
        "extract_required": "Codex Lifeboat is rechtstreeks vanuit het ZIP-bestand gestart.\n\nSluit dit venster, klik met rechts op de gedownloade ZIP, kies 'Alles uitpakken' en start Codex-Lifeboat.exe vanuit de uitgepakte map.",
        "extract_status": "Pak de ZIP eerst volledig uit; starten vanuit de ZIP is geblokkeerd.",
    },
    "en": {
        "title": "Codex Lifeboat",
        "subtitle": "Complete Codex backup and 1-to-1 restore for Windows 10/11",
        "language": "Language",
        "codex_home": "Detected Codex folder",
        "usb": "Detected USB drives",
        "backup": "1. Create complete backup",
        "verify_backup": "2. Verify backup",
        "restore": "3. Complete restore",
        "verify_restore": "4. Verify restore",
        "ready": "Ready",
        "working": "Working… do not close this window.",
        "choose_destination": "Select USB drive or backup destination",
        "choose_backup": "Select the Codex-PortableBackup folder",
        "confirm_backup": "Codex must be fully closed. Create a complete backup of projects, chats and settings in:\n\n{path}?",
        "backup_done": "Backup completed successfully:\n\n{path}",
        "valid_backup": "The backup is complete and valid.\n\nThreads: {threads}\nProjects: {projects}\nHashes: {hashes}",
        "invalid_backup": "The backup is invalid:\n\n{errors}",
        "restore_intro": "Codex must be installed, opened once and signed in on this computer. Close Codex completely before continuing.",
        "restore_confirm": "The safety copy has been created:\n{safety}\n\nCurrent chats: {threads}\nCurrent projects: {projects}\n\nReplace local Codex content with the 1-to-1 backup?",
        "restore_cancelled": "Restore cancelled. The safety copy has been kept.",
        "restore_done": "Restore and final verification succeeded.\n\nSafety copy:\n{safety}",
        "valid_restore": "The restore is valid.\n\nThreads: {threads}\nProjects: {projects}",
        "error": "Error",
        "warning": "Warning",
        "version_warning": "Version check: {message}\n\nInstalled: {installed}\nOnline result: {latest}\n\nContinue anyway?",
        "no_usb": "No removable USB drive was detected automatically; select a folder manually.",
        "detected_backup": "Backup detected automatically:\n\n{path}\n\nUse this backup?",
        "extract_required": "Codex Lifeboat was started directly from the ZIP file.\n\nClose this window, right-click the downloaded ZIP, select 'Extract All', and start Codex-Lifeboat.exe from the extracted folder.",
        "extract_status": "Extract the ZIP completely first; running from inside the ZIP is blocked.",
    },
}


class TransferApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.language = tk.StringVar(value="en")
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.launch_blocked = windows.launched_from_compressed_folder()
        self.last_package: Path | None = None
        self.last_version_check: dict | None = None
        self.geometry("900x650")
        self.minsize(780, 560)
        self._build()
        self._translate()
        self.after(100, self._drain_messages)
        self.after(1000, self._refresh_drives)
        if self.launch_blocked:
            for button in self.action_buttons:
                button.configure(state="disabled")
            self.after(250, self._show_extract_required)

    def t(self, key: str, **values) -> str:
        return TEXT[self.language.get()][key].format(**values)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        header = ttk.Frame(self, padding=(24, 20, 24, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, font=("Segoe UI", 22, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(header, font=("Segoe UI", 10))
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.language_label = ttk.Label(header)
        self.language_label.grid(row=0, column=1, padx=(12, 6))
        self.language_box = ttk.Combobox(
            header,
            state="readonly",
            width=12,
            values=("English", "Nederlands"),
        )
        self.language_box.current(0 if self.language.get() == "en" else 1)
        self.language_box.grid(row=0, column=2)
        self.language_box.bind("<<ComboboxSelected>>", self._change_language)

        detection = ttk.LabelFrame(self, padding=12)
        detection.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        detection.columnconfigure(1, weight=1)
        self.codex_label = ttk.Label(detection)
        self.codex_label.grid(row=0, column=0, sticky="w")
        self.codex_value = ttk.Label(detection, text=str(Path.home() / ".codex"))
        self.codex_value.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.usb_label = ttk.Label(detection)
        self.usb_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        drives = windows.removable_drives()
        self.usb_value = ttk.Label(detection, text=", ".join(map(str, drives)) or "—")
        self.usb_value.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(6, 0))

        buttons = ttk.Frame(self, padding=(24, 8))
        buttons.grid(row=2, column=0, sticky="ew")
        for column in range(2):
            buttons.columnconfigure(column, weight=1)
        self.backup_button = ttk.Button(buttons, command=self._backup)
        self.backup_button.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=6, ipady=12)
        self.verify_backup_button = ttk.Button(buttons, command=self._verify_backup)
        self.verify_backup_button.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=6, ipady=12)
        self.restore_button = ttk.Button(buttons, command=self._restore)
        self.restore_button.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=6, ipady=12)
        self.verify_restore_button = ttk.Button(buttons, command=self._verify_restore)
        self.verify_restore_button.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=6, ipady=12)
        self.action_buttons = (
            self.backup_button,
            self.verify_backup_button,
            self.restore_button,
            self.verify_restore_button,
        )

        status_frame = ttk.Frame(self, padding=(24, 4))
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_frame)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        log_frame = ttk.Frame(self, padding=(24, 8, 24, 20))
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    def _change_language(self, _event=None) -> None:
        self.language.set("en" if self.language_box.current() == 0 else "nl")
        self._translate()

    def _refresh_drives(self) -> None:
        try:
            drives = windows.removable_drives()
            self.usb_value.configure(text=", ".join(map(str, drives)) or "—")
        except Exception:
            pass
        finally:
            self.after(2000, self._refresh_drives)

    def _show_extract_required(self) -> None:
        messagebox.showerror(
            self.t("error"), self.t("extract_required"), parent=self
        )

    def _translate(self) -> None:
        self.title(self.t("title"))
        self.title_label.configure(text=self.t("title"))
        self.subtitle_label.configure(text=self.t("subtitle"))
        self.language_label.configure(text=self.t("language"))
        self.codex_label.configure(text=self.t("codex_home") + ":")
        self.usb_label.configure(text=self.t("usb") + ":")
        self.backup_button.configure(text=self.t("backup"))
        self.verify_backup_button.configure(text=self.t("verify_backup"))
        self.restore_button.configure(text=self.t("restore"))
        self.verify_restore_button.configure(text=self.t("verify_restore"))
        if self.launch_blocked:
            self.status_label.configure(text=self.t("extract_status"))
        else:
            self.status_label.configure(text=self.t("working") if self.busy else self.t("ready"))

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(value))
            elif kind == "progress":
                current, total, message = value
                self.progress.stop()
                self.progress.configure(
                    mode="determinate", maximum=max(int(total), 1), value=int(current)
                )
                self.status_label.configure(text=str(message))
            elif kind == "done":
                self._set_busy(False)
                callback, result = value
                callback(result)
            elif kind == "error":
                self._set_busy(False)
                self._append_log(str(value))
                messagebox.showerror(self.t("error"), str(value), parent=self)
        self.after(100, self._drain_messages)

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        for button in self.action_buttons:
            button.configure(
                state="disabled" if value or self.launch_blocked else "normal"
            )
        if value:
            self.progress.configure(mode="indeterminate", value=0)
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.configure(mode="indeterminate", value=0)
        self._translate()

    def _run(self, function, done) -> None:
        if self.launch_blocked:
            self._show_extract_required()
            return
        if self.busy:
            return
        self._set_busy(True)

        def worker():
            try:
                result = function()
                self.messages.put(("done", (done, result)))
            except Exception as exc:
                self.messages.put(("log", traceback.format_exc()))
                self.messages.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _log_callback(self, message: str) -> None:
        self.messages.put(("log", message))

    def _status_callback(self, current: int, total: int, message: str) -> None:
        self.messages.put(("progress", (current, total, message)))

    def _version_permission(self) -> bool:
        installed = windows.installed_codex_version()
        latest = windows.latest_version_check(installed)
        self.last_version_check = {"installed": installed, "latest": latest}
        if latest.get("isLatest") is not False:
            self._append_log(str(latest.get("message") or "Version check unavailable"))
            return True
        return messagebox.askyesno(
            self.t("warning"),
            self.t(
                "version_warning",
                message=latest.get("message"),
                installed=installed.get("version") or "?",
                latest=latest.get("latestVersion") or "?",
            ),
            parent=self,
        )

    def _initial_destination(self) -> str:
        drives = windows.removable_drives()
        return str(drives[0]) if drives else str(Path.home() / "Documents")

    def _choose_package(self) -> Path | None:
        detected = windows.detect_backup_packages()
        if detected and messagebox.askyesno(
            self.t("verify_backup"),
            self.t("detected_backup", path=detected[0]),
            parent=self,
        ):
            return detected[0]
        initial = str(detected[0].parent if detected else Path.home())
        selected = filedialog.askdirectory(
            title=self.t("choose_backup"), initialdir=initial, parent=self
        )
        return Path(selected) if selected else None

    def _backup(self) -> None:
        if not self._version_permission():
            return
        drives = windows.removable_drives()
        if len(drives) == 1:
            selected = str(drives[0] / "Codex Backups")
        else:
            selected = filedialog.askdirectory(
                title=self.t("choose_destination"),
                initialdir=self._initial_destination(),
                parent=self,
            )
        if not selected:
            return
        if not messagebox.askyesno(
            self.t("backup"), self.t("confirm_backup", path=selected), parent=self
        ):
            return

        def work():
            config_root = Path(tempfile.gettempdir()) / "Codex-Lifeboat"
            config_root.mkdir(parents=True, exist_ok=True)
            config_path = config_root / "backup-config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "configVersion": 1,
                        "destinationRoot": selected,
                        "includeAttachments": True,
                        "projects": [],
                        "additionalPortablePaths": [],
                        "excludeDirectoryNames": [],
                        "versionCheck": self.last_version_check,
                        "knownFolders": {
                            "documents": str(windows.documents_folder()),
                            "desktop": str(windows.desktop_folder()),
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            backup.set_progress_callback(self._log_callback)
            backup.set_status_callback(self._status_callback)
            args = argparse.Namespace(
                config=str(config_path),
                destination=selected,
                source_profile=None,
                source_codex_home=None,
                allow_running_test=False,
            )
            return backup.build_backup(args)

        def done(path):
            self.last_package = Path(path)
            messagebox.showinfo(
                self.t("backup"), self.t("backup_done", path=path), parent=self
            )

        self._run(work, done)

    def _verify_backup(self) -> None:
        package = self._choose_package()
        if not package:
            return

        def done(result):
            if result["valid"]:
                checks = result.get("checks", {})
                messagebox.showinfo(
                    self.t("verify_backup"),
                    self.t(
                        "valid_backup",
                        threads=checks.get("threadsChecked", 0),
                        projects=checks.get("projectsChecked", 0),
                        hashes=checks.get("hashedFilesChecked", 0),
                    ),
                    parent=self,
                )
            else:
                messagebox.showerror(
                    self.t("error"),
                    self.t("invalid_backup", errors="\n".join(result["errors"][:10])),
                    parent=self,
                )

        self._run(
            lambda: validate(
                package,
                False,
                progress=lambda current, total, message: self._status_callback(
                    current, total, message
                ),
            ),
            done,
        )

    def _restore(self) -> None:
        messagebox.showinfo(self.t("restore"), self.t("restore_intro"), parent=self)
        if not self._version_permission():
            return
        package = self._choose_package()
        if not package:
            return

        def work():
            prepared = restore.prepare_restore(
                package, Path.home(), self._log_callback, allow_running_test=False
            )
            confirmation = threading.Event()
            answer: list[bool] = []

            def ask():
                answer.append(
                    messagebox.askyesno(
                        self.t("restore"),
                        self.t(
                            "restore_confirm",
                            safety=prepared["safetyRoot"],
                            threads=prepared["targetThreadsBefore"],
                            projects=prepared["targetProjectsBefore"],
                        ),
                        parent=self,
                    )
                )
                confirmation.set()

            self.after(0, ask)
            confirmation.wait()
            if not answer or not answer[0]:
                return {"cancelled": True, **prepared}
            return restore.restore_backup(
                package,
                Path.home(),
                Path(prepared["safetyRoot"]),
                self._log_callback,
            )

        def done(result):
            if result.get("cancelled"):
                messagebox.showinfo(
                    self.t("restore"), self.t("restore_cancelled"), parent=self
                )
            else:
                self.last_package = package
                messagebox.showinfo(
                    self.t("restore"),
                    self.t("restore_done", safety=result["safetyRoot"]),
                    parent=self,
                )

        self._run(work, done)

    def _verify_restore(self) -> None:
        package = self._choose_package()
        if not package:
            return

        def done(result):
            if result["valid"]:
                messagebox.showinfo(
                    self.t("verify_restore"),
                    self.t(
                        "valid_restore",
                        threads=result["checks"].get("threads", 0),
                        projects=result["checks"].get("projects", 0),
                    ),
                    parent=self,
                )
            else:
                messagebox.showerror(
                    self.t("error"), "\n".join(result["errors"][:10]), parent=self
                )

        self._run(lambda: restore.verify_restored(package, Path.home()), done)


def run_gui() -> None:
    app = TransferApp()
    app.mainloop()
