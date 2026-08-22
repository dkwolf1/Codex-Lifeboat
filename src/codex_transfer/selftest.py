from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import backup, restore
from .validate import validate


THREAD_ID = "self-test-thread-001"
PROJECT_ID = "self-test-project"


def _hash_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = backup.sha256_file(path)
    return result


def _write_source(profile: Path) -> tuple[Path, Path]:
    codex = profile / ".codex"
    project = profile / "Documents" / "DemoProject"
    session = codex / "sessions" / "2026" / "08" / "22" / "rollout-self-test.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text("# New project\n", encoding="utf-8")
    (project / ".env").write_text("SECRET=self-test\n", encoding="utf-8")
    (project / ".git" / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-22T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": THREAD_ID,
                    "cwd": str(project),
                    "originator": "Codex Desktop",
                    "cli_version": "self-test",
                },
            },
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-08-22T10:00:01Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": f"Open {project}"},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (codex / "session_index.jsonl").write_text(
        json.dumps({"id": THREAD_ID, "title": "Self test"}) + "\n",
        encoding="utf-8",
    )
    (codex / ".codex-global-state.json").write_text(
        json.dumps(
            {
                "local-projects": {
                    PROJECT_ID: {"name": "DemoProject", "rootPaths": [str(project)]}
                },
                "project-order": [PROJECT_ID],
                "thread-project-assignments": {THREAD_ID: {"projectId": PROJECT_ID}},
                "electron-main-window-bounds": {"x": 1, "y": 2},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (codex / "skills" / "demo").mkdir(parents=True)
    (codex / "skills" / "demo" / "SKILL.md").write_text("# demo skill\n", encoding="utf-8")
    (codex / "config.toml").write_text("model = 'self-test'\n", encoding="utf-8")
    (codex / "auth.json").write_text('{"secret":"SOURCE-MUST-NOT-COPY"}\n', encoding="utf-8")
    database = sqlite3.connect(codex / "state_5.sqlite")
    database.executescript(
        """
        CREATE TABLE _sqlx_migrations (
          version INTEGER PRIMARY KEY, description TEXT NOT NULL,
          installed_on TEXT NOT NULL, success INTEGER NOT NULL,
          checksum BLOB NOT NULL, execution_time INTEGER NOT NULL
        );
        CREATE TABLE thread_sections (id TEXT PRIMARY KEY, name TEXT NOT NULL, appearance TEXT);
        CREATE TABLE projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata TEXT NOT NULL,
          position INTEGER NOT NULL, created_at_ms INTEGER NOT NULL,
          updated_at_ms INTEGER NOT NULL
        );
        CREATE TABLE project_roots (
          project_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL,
          PRIMARY KEY(project_id,position)
        );
        CREATE TABLE threads (
          id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          cwd TEXT NOT NULL, title TEXT NOT NULL, archived INTEGER NOT NULL,
          project_id TEXT, cli_version TEXT NOT NULL,
          first_user_message TEXT NOT NULL
        );
        CREATE TABLE thread_dynamic_tools (
          thread_id TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL,
          description TEXT NOT NULL, input_schema TEXT NOT NULL,
          defer_loading INTEGER NOT NULL, PRIMARY KEY(thread_id,position)
        );
        CREATE TABLE thread_spawn_edges (
          parent_thread_id TEXT NOT NULL, child_thread_id TEXT PRIMARY KEY,
          status TEXT NOT NULL
        );
        """
    )
    database.execute(
        "INSERT INTO _sqlx_migrations VALUES(1,'self-test','2026-08-22',1,?,1)",
        (b"self-test",),
    )
    database.execute(
        "INSERT INTO projects VALUES(?,?,?,?,?,?)",
        (PROJECT_ID, "DemoProject", "{}", 0, 1, 1),
    )
    database.execute(
        "INSERT INTO project_roots VALUES(?,?,?)", (PROJECT_ID, 0, str(project))
    )
    database.execute(
        "INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            THREAD_ID,
            str(session),
            1,
            2,
            str(project),
            "Self test",
            0,
            PROJECT_ID,
            "self-test",
            "hello",
        ),
    )
    database.commit()
    database.close()
    return codex, project


def _write_target(profile: Path, marker: str) -> tuple[Path, Path]:
    codex = profile / ".codex"
    project = profile / "Documents" / "DemoProject"
    project.mkdir(parents=True, exist_ok=True)
    (project / "OLD.txt").write_text(marker, encoding="utf-8")
    codex.mkdir(parents=True, exist_ok=True)
    (codex / "auth.json").write_text(
        json.dumps({"secret": f"TARGET-{marker}"}) + "\n", encoding="utf-8"
    )
    (codex / "installation_id").write_text(f"INSTALL-{marker}\n", encoding="utf-8")
    (codex / ".codex-global-state.json").write_text(
        json.dumps({"electron-main-window-bounds": {"x": 99, "y": 99}}), encoding="utf-8"
    )
    database = sqlite3.connect(codex / "state_5.sqlite")
    database.executescript(
        """
        CREATE TABLE _sqlx_migrations (
          version INTEGER PRIMARY KEY, description TEXT NOT NULL,
          installed_on TEXT NOT NULL, success INTEGER NOT NULL,
          checksum BLOB NOT NULL, execution_time INTEGER NOT NULL
        );
        CREATE TABLE thread_sections (id TEXT PRIMARY KEY, name TEXT NOT NULL, appearance TEXT);
        CREATE TABLE projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata TEXT NOT NULL,
          position INTEGER NOT NULL, created_at_ms INTEGER NOT NULL,
          updated_at_ms INTEGER NOT NULL
        );
        CREATE TABLE project_roots (
          project_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL,
          PRIMARY KEY(project_id,position)
        );
        CREATE TABLE threads (
          id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          cwd TEXT NOT NULL, title TEXT NOT NULL, archived INTEGER NOT NULL,
          project_id TEXT, cli_version TEXT NOT NULL,
          first_user_message TEXT NOT NULL,
          preview TEXT NOT NULL, recency_at INTEGER NOT NULL,
          recency_at_ms INTEGER NOT NULL, history_mode TEXT NOT NULL,
          memory_mode TEXT NOT NULL, is_pinned INTEGER NOT NULL
        );
        CREATE TABLE thread_dynamic_tools (
          thread_id TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL,
          description TEXT NOT NULL, input_schema TEXT NOT NULL,
          defer_loading INTEGER NOT NULL, PRIMARY KEY(thread_id,position)
        );
        CREATE TABLE thread_spawn_edges (
          parent_thread_id TEXT NOT NULL, child_thread_id TEXT PRIMARY KEY,
          status TEXT NOT NULL
        );
        """
    )
    database.execute(
        "INSERT INTO _sqlx_migrations VALUES(2,'target','2026-08-22',1,?,1)",
        (b"target",),
    )
    database.execute(
        "INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            f"old-{marker}",
            str(codex / "sessions" / "old.jsonl"),
            1,
            1,
            str(project),
            "Old",
            0,
            None,
            "target",
            "old",
            "old",
            1,
            1000,
            "full",
            "disabled",
            0,
        ),
    )
    database.commit()
    database.close()
    return codex, project


def _write_older_target(profile: Path, marker: str) -> tuple[Path, Path]:
    codex = profile / ".codex"
    project = profile / "Documents" / "DemoProject"
    project.mkdir(parents=True, exist_ok=True)
    (project / "OLD.txt").write_text(marker, encoding="utf-8")
    codex.mkdir(parents=True, exist_ok=True)
    (codex / "auth.json").write_text(
        json.dumps({"secret": f"TARGET-{marker}"}) + "\n", encoding="utf-8"
    )
    (codex / ".codex-global-state.json").write_text("{}\n", encoding="utf-8")
    database = sqlite3.connect(codex / "state_5.sqlite")
    database.executescript(
        """
        CREATE TABLE _sqlx_migrations (
          version INTEGER PRIMARY KEY, description TEXT NOT NULL,
          installed_on TEXT NOT NULL, success INTEGER NOT NULL,
          checksum BLOB NOT NULL, execution_time INTEGER NOT NULL
        );
        CREATE TABLE thread_sections (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata TEXT NOT NULL,
          position INTEGER NOT NULL, created_at_ms INTEGER NOT NULL,
          updated_at_ms INTEGER NOT NULL
        );
        CREATE TABLE project_roots (
          project_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL,
          PRIMARY KEY(project_id,position)
        );
        CREATE TABLE threads (
          id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          cwd TEXT NOT NULL, title TEXT NOT NULL, archived INTEGER NOT NULL,
          project_id TEXT, cli_version TEXT NOT NULL
        );
        CREATE TABLE thread_dynamic_tools (
          thread_id TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL,
          description TEXT NOT NULL, input_schema TEXT NOT NULL,
          defer_loading INTEGER NOT NULL, PRIMARY KEY(thread_id,position)
        );
        CREATE TABLE thread_spawn_edges (
          parent_thread_id TEXT NOT NULL, child_thread_id TEXT PRIMARY KEY,
          status TEXT NOT NULL
        );
        """
    )
    database.execute(
        "INSERT INTO _sqlx_migrations VALUES(0,'older-target','2026-08-22',1,?,1)",
        (b"older",),
    )
    database.commit()
    database.close()
    return codex, project


def _gui_smoke_test() -> bool:
    # Tcl/Tk teardown can wait indefinitely inside a hidden PyInstaller one-file
    # child process. The actual bilingual widget test runs in the source test;
    # the packaged build is smoke-tested separately by opening its real window.
    if getattr(sys, "frozen", False):
        return True
    from .gui import TransferApp

    app = TransferApp()
    try:
        app.withdraw()
        app.update_idletasks()
        app.language.set("nl")
        app._translate()
        dutch = app.backup_button.cget("text") == "1. Volledige back-up maken"
        app.language.set("en")
        app._translate()
        english = app.backup_button.cget("text") == "1. Create complete backup"
        return bool(dutch and english and len(app.action_buttons) == 4)
    finally:
        app.destroy()


def run_self_test(work_root: Path | None = None) -> dict[str, Any]:
    root = (
        work_root.resolve()
        if work_root
        else Path(tempfile.mkdtemp(prefix="codex-transfer-selftest-"))
    )
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"Self-test work directory must be empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    source_profile = root / "source-user"
    target_profile = root / "target-user"
    rollback_profile = root / "rollback-user"
    older_target_profile = root / "older-target-user"
    source_codex, source_project = _write_source(source_profile)
    _, target_project = _write_target(target_profile, "PRESERVE-A")
    _, rollback_project = _write_target(rollback_profile, "PRESERVE-B")
    _write_older_target(older_target_profile, "OLDER")
    source_before = _hash_tree(source_profile)
    destination = root / "usb"
    config = root / "backup-config.json"
    config.write_text(
        json.dumps(
            {
                "configVersion": 1,
                "destinationRoot": str(destination),
                "includeAttachments": True,
                "projects": [],
                "additionalPortablePaths": [],
                "excludeDirectoryNames": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config=str(config),
        destination=str(destination),
        source_profile=str(source_profile),
        source_codex_home=str(source_codex),
        allow_running_test=True,
    )
    package = backup.build_backup(args)
    source_after = _hash_tree(source_profile)
    package_validation = validate(package, False)
    snapshot_connection = backup.connect_read_only(
        package / "codex" / "state.snapshot.sqlite"
    )
    try:
        snapshot_journal_mode = str(
            snapshot_connection.execute("PRAGMA journal_mode").fetchone()[0]
        ).lower()
    finally:
        snapshot_connection.close()
    source_auth_in_package = any(
        path.name.lower() == "auth.json" for path in package.rglob("*") if path.is_file()
    )
    portable_executable_included = True
    if getattr(sys, "frozen", False):
        packaged_executable = package / "tools" / "Codex-Lifeboat.exe"
        staged_executable = backup.stage_runtime_executable()
        portable_executable_included = bool(
            staged_executable
            and packaged_executable.is_file()
            and backup.sha256_file(packaged_executable)
            == backup.sha256_file(staged_executable)
        )
    auth_hash_before = backup.sha256_file(target_profile / ".codex" / "auth.json")
    prepared = restore.prepare_restore(
        package, target_profile, allow_running_test=True
    )
    restored = restore.restore_backup(
        package, target_profile, Path(prepared["safetyRoot"])
    )
    restored_validation = restore.verify_restored(package, target_profile)
    auth_preserved = (
        auth_hash_before == backup.sha256_file(target_profile / ".codex" / "auth.json")
    )
    project_exact = (
        (target_project / "README.md").read_text(encoding="utf-8") == "# New project\n"
        and (target_project / ".env").read_text(encoding="utf-8") == "SECRET=self-test\n"
        and not (target_project / "OLD.txt").exists()
    )
    portable_profile_restored = (
        (target_profile / ".codex" / "config.toml").is_file()
        and (target_profile / ".codex" / "skills" / "demo" / "SKILL.md").is_file()
    )

    older_prepared = restore.prepare_restore(
        package, older_target_profile, allow_running_test=True
    )
    restore.restore_backup(
        package, older_target_profile, Path(older_prepared["safetyRoot"])
    )
    older_schema_restore_valid = restore.verify_restored(
        package, older_target_profile
    )["valid"]

    tampered = root / "tampered-package"
    shutil.copytree(package, tampered)
    tamper_target = next((tampered / "projects").rglob("README.md"))
    tamper_target.write_text("tampered\n", encoding="utf-8")
    tamper_rejected = not validate(tampered, False)["valid"]

    rollback_auth_before = backup.sha256_file(rollback_profile / ".codex" / "auth.json")
    rollback_prepared = restore.prepare_restore(
        package, rollback_profile, allow_running_test=True
    )
    rollback_triggered = False
    try:
        restore.restore_backup(
            package,
            rollback_profile,
            Path(rollback_prepared["safetyRoot"]),
            fail_after_database_for_test=True,
        )
    except Exception:
        rollback_triggered = True
    rollback_preserved = (
        rollback_triggered
        and (rollback_project / "OLD.txt").read_text(encoding="utf-8") == "PRESERVE-B"
        and backup.sha256_file(rollback_profile / ".codex" / "auth.json")
        == rollback_auth_before
        and backup.read_json(Path(rollback_prepared["safetyRoot"]) / "restore-journal.json")[
            "status"
        ]
        == "rolled-back"
    )
    checks = {
        "packageValid": package_validation["valid"],
        "snapshotUsesSingleFileJournal": snapshot_journal_mode == "delete",
        "validatorIsReadOnly": package_validation.get("checks", {}).get(
            "packageUnchangedDuringValidation", False
        ),
        "sourceUnchanged": source_before == source_after,
        "sourceAuthExcluded": not source_auth_in_package,
        "portableExecutableIncluded": portable_executable_included,
        "restoreValid": restored_validation["valid"],
        "targetAuthPreserved": auth_preserved,
        "projectExact": project_exact,
        "portableProfileRestored": portable_profile_restored,
        "tamperRejected": tamper_rejected,
        "rollbackTriggeredAndPreserved": rollback_preserved,
        "safetyCopyKept": Path(prepared["safetyRoot"]).is_dir(),
        "newerSourceToOlderTarget": older_schema_restore_valid,
        "dutchEnglishGui": _gui_smoke_test(),
    }
    result = {
        "passed": all(checks.values()),
        "workRoot": str(root),
        "package": str(package),
        "checks": checks,
        "restore": restored,
    }
    backup.write_json(root / "self-test-result.json", result)
    return result
