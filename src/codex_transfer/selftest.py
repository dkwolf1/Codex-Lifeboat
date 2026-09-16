from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from unittest import mock
from pathlib import Path
from typing import Any

from . import (
    backup,
    compatibility_matrix,
    conversation_prefix,
    diagnostics,
    atomic_io,
    git_insight,
    lineage,
    location_mapper,
    path_model,
    portability_audit,
    project_identity,
    recovery,
    restore,
    restore_plan,
    windows,
)
from .validate import supports_format, validate


THREAD_ID = "self-test-thread-001"
PROJECTLESS_THREAD_ID = "self-test-thread-projectless-002"
ARCHIVED_THREAD_ID = "self-test-thread-archived-003"
PROJECT_ID = "self-test-project"
DESTINATION_ONLY_THREAD_ID = "self-test-destination-only-004"
DESTINATION_ONLY_PROJECT_ID = "self-test-destination-project"


def _hash_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = backup.sha256_file(path)
    return result


def _conversation_snapshot(profile: Path) -> dict[str, Any]:
    database = profile / ".codex" / "state_5.sqlite"
    connection = sqlite3.connect(database)
    try:
        columns = {
            str(row[1]) for row in connection.execute('PRAGMA table_info("threads")')
        }
        selected = [
            name
            for name in ("id", "rollout_path", "title", "archived", "is_pinned", "project_id")
            if name in columns
        ]
        rows = connection.execute(
            "SELECT " + ",".join(f'"{name}"' for name in selected) + ' FROM "threads" ORDER BY "id"'
        ).fetchall()
        tools = (
            connection.execute(
                'SELECT "thread_id","position","name" FROM "thread_dynamic_tools" '
                'ORDER BY "thread_id","position"'
            ).fetchall()
            if connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='thread_dynamic_tools'"
            ).fetchone()[0]
            else []
        )
        edges = (
            connection.execute(
                'SELECT "parent_thread_id","child_thread_id","status" '
                'FROM "thread_spawn_edges" ORDER BY "parent_thread_id","child_thread_id"'
            ).fetchall()
            if connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='thread_spawn_edges'"
            ).fetchone()[0]
            else []
        )
    finally:
        connection.close()
    rollouts: dict[str, str | None] = {}
    for row in rows:
        thread_id = str(row[0])
        rollout = Path(str(row[1]).replace("\\\\?\\", "")) if row[1] else None
        rollouts[thread_id] = (
            backup.sha256_file(rollout) if rollout and rollout.is_file() else None
        )
    return {
        "columns": selected,
        "rows": [list(row) for row in rows],
        "tools": [list(row) for row in tools],
        "edges": [list(row) for row in edges],
        "rollouts": rollouts,
        "sessionIndex": (
            backup.sha256_file(profile / ".codex" / "session_index.jsonl")
            if (profile / ".codex" / "session_index.jsonl").is_file()
            else None
        ),
    }


def _copy_profile_fixture(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    database = destination / ".codex" / "state_5.sqlite"
    connection = sqlite3.connect(database)
    try:
        for table, column in (
            ("threads", "rollout_path"),
            ("threads", "cwd"),
            ("project_roots", "path"),
        ):
            if not connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]:
                continue
            connection.execute(
                f'UPDATE "{table}" SET "{column}"=replace("{column}",?,?)',
                (str(source), str(destination)),
            )
        connection.commit()
    finally:
        connection.close()


def _add_destination_conversation(
    profile: Path,
    thread_id: str = DESTINATION_ONLY_THREAD_ID,
    title: str = "Destination-only pinned archive",
) -> Path:
    codex = profile / ".codex"
    project = profile / "Documents" / "DestinationOnlyProject"
    project.mkdir(parents=True, exist_ok=True)
    (project / "LOCAL.txt").write_text("destination project\n", encoding="utf-8")
    rollout = codex / "archived_sessions" / f"rollout-{thread_id}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    rollout.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-23T11:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "cwd": str(project),
                    "originator": "Codex Desktop",
                    "cli_version": "destination-test",
                },
            },
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {
                "timestamp": "2026-08-23T11:00:01Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "destination only"},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    connection = sqlite3.connect(codex / "state_5.sqlite")
    try:
        connection.execute(
            "INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?)",
            (
                DESTINATION_ONLY_PROJECT_ID,
                "Destination-only project",
                "{}",
                9,
                3,
                3,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO project_roots VALUES(?,?,?)",
            (DESTINATION_ONLY_PROJECT_ID, 0, str(project)),
        )
        connection.execute(
            "INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                thread_id,
                str(rollout),
                3,
                3,
                str(project),
                title,
                1,
                DESTINATION_ONLY_PROJECT_ID,
                "destination-test",
                "destination only",
                "destination only",
                3,
                3000,
                "full",
                "disabled",
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return rollout


def _add_registered_destination_project(
    profile: Path,
    marker: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    codex_project_id = f"destination-project-{marker.lower()}"
    project = project_root or (
        profile / "Documents" / f"DestinationProject-{marker}"
    )
    project.mkdir(parents=True, exist_ok=True)
    (project / "LOCAL.txt").write_text(
        f"destination-only {marker}\n", encoding="utf-8"
    )
    (project / "nested").mkdir()
    (project / "nested" / "STATE.txt").write_text(
        f"retain exactly {marker}\n", encoding="utf-8"
    )
    connection = sqlite3.connect(profile / ".codex" / "state_5.sqlite")
    try:
        connection.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?,?)",
            (codex_project_id, project.name, "{}", 20, 20, 20),
        )
        connection.execute(
            "INSERT INTO project_roots VALUES(?,?,?)",
            (codex_project_id, 0, str(project)),
        )
        connection.commit()
    finally:
        connection.close()
    global_state_path = profile / ".codex" / ".codex-global-state.json"
    global_state = backup.read_json(global_state_path)
    global_state.setdefault("local-projects", {})[codex_project_id] = {
        "name": project.name,
        "rootPaths": [str(project)],
    }
    if codex_project_id not in global_state.setdefault("project-order", []):
        global_state["project-order"].append(codex_project_id)
    backup.write_json(global_state_path, global_state)
    registry_path = windows.project_registry_path(profile)
    registry = project_identity.load_registry(registry_path)
    assignment = project_identity.assign_identity(
        registry, project, project.name, [codex_project_id]
    )
    project_identity.save_registry(registry_path, registry)
    return {
        "path": project,
        "hashes": _hash_tree(project),
        "codexProjectId": codex_project_id,
        "projectIdentityId": assignment["projectId"],
        "rootId": assignment["rootId"],
        "registryPath": registry_path,
    }


def _project_registration_state(profile: Path, codex_project_id: str) -> dict[str, bool]:
    connection = sqlite3.connect(profile / ".codex" / "state_5.sqlite")
    try:
        database_project = bool(
            connection.execute(
                "SELECT count(*) FROM projects WHERE id=?", (codex_project_id,)
            ).fetchone()[0]
        )
        database_root = bool(
            connection.execute(
                "SELECT count(*) FROM project_roots WHERE project_id=?",
                (codex_project_id,),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    global_state = backup.read_json(
        profile / ".codex" / ".codex-global-state.json"
    )
    return {
        "databaseProject": database_project,
        "databaseRoot": database_root,
        "globalProject": codex_project_id
        in (global_state.get("local-projects") or {}),
        "globalOrder": codex_project_id in (global_state.get("project-order") or []),
    }


def _write_recovery_fixture(
    profile: Path,
    source_database: Path,
    name: str,
    sequence: int,
    status: str = "complete",
    include_staging: bool = False,
    include_visible_archive: bool = False,
) -> dict[str, Path]:
    point = windows.recovery_points_folder(profile) / name
    codex_before = point / "codex-before-restore"
    codex_before.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_database, codex_before / "state_5.sqlite")
    target = profile / "Documents" / f"Active-{name}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "ACTIVE.txt").write_text(name, encoding="utf-8")
    payload = (
        profile
        / "Documents"
        / ".codex-lifeboat-recovery"
        / name
        / "project-before"
    )
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "RECOVERY.txt").write_text(name, encoding="utf-8")
    staging = target.parent / f".codex-lifeboat-stage-test-{name}"
    if include_staging:
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "STALE.txt").write_text("verified stale stage", encoding="utf-8")
    projects: list[dict[str, Any]] = [
        {
            "id": f"fixture-{name}",
            "target": str(target),
            "existedBefore": True,
            "strategy": "transactional-mirror",
            "stagingPath": str(staging),
            "quarantinePath": str(payload),
            "previousTargetDisposition": "recovery",
            "status": "complete",
        }
    ]
    visible_archive = profile / "Documents" / "Codex Lifeboat Project Archives" / name
    if include_visible_archive:
        visible_archive.mkdir(parents=True, exist_ok=True)
        (visible_archive / "ARCHIVE.txt").write_text(name, encoding="utf-8")
        archive_target = profile / "Documents" / f"ArchiveActive-{name}"
        archive_target.mkdir(parents=True, exist_ok=True)
        projects.append(
            {
                "id": f"archive-{name}",
                "target": str(archive_target),
                "existedBefore": True,
                "strategy": "transactional-mirror",
                "stagingPath": str(archive_target.parent / f".codex-lifeboat-stage-archive-{name}"),
                "quarantinePath": str(visible_archive),
                "previousTargetDisposition": "archive",
                "status": "complete",
            }
        )
    backup.write_json(
        point / "restore-journal.json",
        {
            "preparedAtUtc": f"2026-08-23T10:0{sequence}:00Z",
            "completedAtUtc": f"2026-08-23T10:0{sequence}:30Z",
            "package": str(profile / "usb" / f"Codex-PortableBackup-{name}"),
            "targetProfile": str(profile),
            "safetyRoot": str(point),
            "status": status,
            "projects": projects,
        },
    )
    return {
        "point": point,
        "payload": payload,
        "staging": staging,
        "visibleArchive": visible_archive,
    }


def _change_destination_conversation(profile: Path, thread_id: str) -> Path:
    connection = sqlite3.connect(profile / ".codex" / "state_5.sqlite")
    try:
        row = connection.execute(
            "SELECT rollout_path FROM threads WHERE id=?", (thread_id,)
        ).fetchone()
        if not row:
            raise RuntimeError(f"Fixture conversation not found: {thread_id}")
        rollout = Path(str(row[0]).replace("\\\\?\\", ""))
        connection.execute(
            "UPDATE threads SET title=?,is_pinned=1 WHERE id=?",
            ("Destination independently edited", thread_id),
        )
        connection.commit()
    finally:
        connection.close()
    with rollout.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-08-23T12:00:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "independent destination edit",
                    },
                },
                separators=(",", ":"),
            )
            + "\n"
        )
    return rollout


def _write_source(profile: Path) -> tuple[Path, Path]:
    codex = profile / ".codex"
    project = profile / "Documents" / "DemoProject"
    session = codex / "sessions" / "2026" / "08" / "22" / "rollout-self-test.jsonl"
    projectless_session = (
        codex / "sessions" / "2026" / "08" / "23" / "rollout-projectless.jsonl"
    )
    archived_session = (
        codex / "archived_sessions" / "rollout-archived-self-test.jsonl"
    )
    session.parent.mkdir(parents=True, exist_ok=True)
    projectless_session.parent.mkdir(parents=True, exist_ok=True)
    archived_session.parent.mkdir(parents=True, exist_ok=True)
    (codex / "dictation-history").mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(parents=True, exist_ok=True)
    (project / "README.md").write_text("# New project\n", encoding="utf-8")
    (project / ".env").write_text("SECRET=self-test\n", encoding="utf-8")
    (project / ".git" / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
    attachment = profile / "AppData" / "Local" / "Temp" / "codex-selftest.png"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b"self-test-image")
    missing_attachment = attachment.with_name("codex-missing-selftest.png")

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
                "payload": {
                    "type": "user_message",
                    "message": f"{attachment}; {missing_attachment}",
                },
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    projectless_session.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-23T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": PROJECTLESS_THREAD_ID,
                    "cwd": str(project),
                    "originator": "Codex Desktop",
                    "cli_version": "self-test",
                },
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    archived_session.write_text(
        json.dumps(
            {
                "timestamp": "2026-08-21T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": ARCHIVED_THREAD_ID,
                    "cwd": str(project),
                    "originator": "Codex Desktop",
                    "cli_version": "self-test",
                },
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    (codex / "session_index.jsonl").write_text(
        json.dumps({"id": THREAD_ID, "title": "Self test"})
        + "\n"
        + json.dumps({"id": PROJECTLESS_THREAD_ID, "title": "Pinned projectless"})
        + "\n",
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
                "projectless-thread-ids": [PROJECTLESS_THREAD_ID, ARCHIVED_THREAD_ID],
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
    database.executemany(
        "INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                THREAD_ID, str(session), 1, 2, str(project), "Self test", 0,
                PROJECT_ID, "self-test", "hello", "main", 2, 2000,
                "full", "disabled", 0,
            ),
            (
                PROJECTLESS_THREAD_ID, str(projectless_session), 3, 4,
                str(project), "Pinned projectless", 0, None, "self-test",
                "projectless", "pinned", 4, 4000, "full", "disabled", 1,
            ),
            (
                ARCHIVED_THREAD_ID, str(archived_session), 0, 1, str(project),
                "Archived projectless", 1, None, "self-test", "archived",
                "archived", 1, 1000, "full", "disabled", 0,
            ),
        ],
    )
    database.execute(
        "INSERT INTO thread_sections VALUES(?,?,?)", ("recent", "Recent", "default")
    )
    database.execute(
        "INSERT INTO thread_dynamic_tools VALUES(?,?,?,?,?,?)",
        (THREAD_ID, 0, "self-test-tool", "fixture", "{}", 0),
    )
    database.execute(
        "INSERT INTO thread_spawn_edges VALUES(?,?,?)",
        (THREAD_ID, PROJECTLESS_THREAD_ID, "completed"),
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


def _progress_model_test() -> bool:
    from .gui import TransferApp, weighted_operation_progress

    progress = weighted_operation_progress(0, 0, 5, 10)
    progress = weighted_operation_progress(progress, 1, 0, 0)
    copy_start = progress
    progress = weighted_operation_progress(progress, 3, 50, 100)
    measured = progress
    progress = weighted_operation_progress(progress, 3, 0, 0)
    progress = weighted_operation_progress(progress, 4, 1, 1)
    return bool(
        copy_start >= 15
        and measured >= copy_start
        and progress == 100
        and TransferApp._progress_stage("Scanning project 1/3") == 0
        and TransferApp._progress_stage("Step 3/6 — Copying conversations") == 1
        and TransferApp._progress_stage("Inventorying conversation attachments") == 2
        and TransferApp._progress_stage("Hashing backup: 5/10") == 3
        and TransferApp._progress_stage("Backup complete") == 4
    )


def _gui_smoke_test() -> bool:
    # Tcl/Tk teardown can wait indefinitely inside a hidden PyInstaller one-file
    # child process. The actual bilingual widget test runs in the source test;
    # the packaged build is smoke-tested separately by opening its real window.
    if getattr(sys, "frozen", False):
        return True
    from .gui import (
        BackupResultDialog,
        BackupSelectionDialog,
        DiagnosticsDialog,
        PathPortabilityDialog,
        RecoveryDialog,
        RestorePlanDialog,
        TransferApp,
    )

    app = TransferApp()
    try:
        app.withdraw()
        app.update_idletasks()
        app.language.set("nl")
        app._translate()
        dutch = bool(
            app.backup_button.cget("text") == "Naar back-ups"
            and app.overview_title.cget("text") == "Overzicht"
            and app.t("map_external_title") == "Projectlocatie kiezen"
            and "veilig" in app.t("map_external_invalid", errors="test")
            and app.t("plan_restore") == "Plan goedkeuren en doorgaan"
            and app.t("keep_both") == "Beide bewaren"
            and app.t("archive") == "Project archiveren"
            and app.t("delete") == "Project verwijderen"
            and app.t("recovery") == "Herstelpunten"
            and app.t("diagnostics") == "Diagnose"
        )
        app.language.set("en")
        app._translate()
        english = bool(
            app.backup_button.cget("text") == "Open backups"
            and app.overview_title.cget("text") == "Overview"
            and app.t("map_external_title") == "Choose project location"
            and "safely" in app.t("map_external_invalid", errors="test")
            and app.t("plan_restore") == "Approve plan and continue"
            and app.t("keep_both") == "Keep both"
            and app.t("archive") == "Archive project"
            and app.t("delete") == "Delete project"
            and app.t("recovery") == "Recovery points"
            and app.t("diagnostics") == "Diagnostics"
        )
        app._show_tab("overview")
        app.backup_button.invoke()
        opened_backup_tab = app.current_tab == "backup"
        app.nav_restore_button.invoke()
        opened_restore_tab = app.current_tab == "restore"
        app.nav_recovery_button.invoke()
        opened_recovery_tab = app.current_tab == "recovery"
        app.nav_diagnostics_button.invoke()
        opened_diagnostics_tab = app.current_tab == "diagnostics"
        navigation_tabs = bool(
            opened_backup_tab
            and opened_restore_tab
            and opened_recovery_tab
            and opened_diagnostics_tab
        )
        app._show_tab("overview")
        app._begin_operation("backup")
        app._set_busy(True)
        app._apply_progress(50, 100, "Hashing backup: 5/10 files")
        measured_progress = float(app.progress.cget("value"))
        app._apply_progress(0, 0, "Step 5/6 — Checking package structure")
        progress_ui_stable = bool(
            str(app.progress.cget("mode")) == "determinate"
            and float(app.progress.cget("value")) >= measured_progress
            and app.progress_percent.cget("text").endswith("%")
            and app.stage_labels[3].cget("foreground") == app.NAVY
        )
        app._finish_operation(True)
        app._set_busy(False)
        blocked_dialog = RestorePlanDialog(
            app,
            {
                "ready": False,
                "items": [{
                    "name": "Conflict", "kind": "project", "state": "conflicting",
                    "source": "A", "target": "B", "proposedAction": "resolve",
                    "sourceBytes": 1, "blocking": True,
                }],
                "diskRequirements": [],
                "blockingReasons": ["test conflict"],
            },
        )
        app.update_idletasks()
        blocked_is_disabled = blocked_dialog.approve_button.instate(["disabled"])
        blocked_dialog.destroy()
        ready_dialog = RestorePlanDialog(
            app,
            {
                "ready": True,
                "items": [],
                "diskRequirements": [],
                "blockingReasons": [],
            },
        )
        app.update_idletasks()
        ready_is_enabled = not ready_dialog.approve_button.instate(["disabled"])
        ready_dialog.destroy()
        decision_dialog = RestorePlanDialog(
            app,
            {
                "planVersion": restore_plan.PLAN_VERSION,
                "backupId": "test",
                "package": "test",
                "targetProfile": "test",
                "ready": False,
                "cancelled": False,
                "items": [{
                    "key": "conversation/test", "name": "Chat conflict",
                    "kind": "conversation", "state": "conflicting",
                    "source": "A", "target": "B", "proposedAction": "resolve",
                    "sourceBytes": 1, "targetBytes": 1, "requiredBytes": 1,
                    "blocking": True, "reason": "test conflict",
                    "decision": None,
                    "availableDecisions": list(restore_plan.CONVERSATION_DECISIONS),
                }],
                "diskRequirements": [],
                "blockingReasons": ["test conflict"],
                "writeSet": [],
                "locationPlan": {"issues": [], "requiredExternalRoots": []},
            },
        )
        decision_dialog.plan_tree.selection_set("conversation/test")
        decision_dialog._selection_changed()
        decision_button_enabled = not decision_dialog.decision_buttons[
            "keep-target"
        ].instate(["disabled"])
        decision_dialog._apply_decision("keep-target")
        decision_resolved = bool(
            decision_dialog.plan.get("ready")
            and not decision_dialog.approve_button.instate(["disabled"])
        )
        decision_dialog.destroy()
        project_dialog = RestorePlanDialog(
            app,
            {
                "planVersion": restore_plan.PLAN_VERSION,
                "backupId": "test",
                "package": "test",
                "targetProfile": "test",
                "ready": False,
                "cancelled": False,
                "items": [{
                    "key": "project/test", "name": "Project conflict",
                    "kind": "project", "state": "conflicting",
                    "source": "A", "target": "B", "proposedAction": "resolve",
                    "sourceBytes": 1, "targetBytes": 1, "requiredBytes": 1,
                    "blocking": True, "reason": "test conflict",
                    "decision": None,
                    "availableDecisions": list(
                        restore_plan.PROJECT_DECISIONS_CONFLICT
                    ),
                }],
                "diskRequirements": [],
                "blockingReasons": ["test conflict"],
                "writeSet": [],
                "locationPlan": {"issues": [], "requiredExternalRoots": []},
            },
        )
        project_dialog.plan_tree.selection_set("project/test")
        project_dialog._selection_changed()
        archive_button_enabled = not project_dialog.decision_buttons[
            "archive"
        ].instate(["disabled"])
        project_dialog._apply_decision("archive")
        project_decision_resolved = bool(
            project_dialog.plan.get("ready")
            and next(
                item
                for item in project_dialog.plan["items"]
                if item.get("key") == "project/test"
            ).get("proposedAction") == "archive-and-replace"
        )
        project_dialog.destroy()
        result_model = {
            "package": "C:/backup",
            "report": "C:/backup/reports/backup-report.json",
            "valid": True,
            "warningCount": 2,
            "warnings": {
                "missingAttachments": 2, "links": 0,
                "missingProjects": 0, "other": 0,
            },
            "metrics": {"chats": 3, "projects": 1, "files": 20, "bytes": 1024},
            "conversations": {"active": 2, "archived": 1, "pinned": 1, "projectless": 2},
            "attachments": {"copied": 1, "missing": 2},
            "identities": {"logical": 1, "roots": 1},
            "lineage": "linear",
        }
        result_dialog = BackupResultDialog(app, result_model, True)
        app.update_idletasks()
        result_dialog_created = result_dialog.winfo_exists() == 1
        result_dialog.destroy()
        selection_dialog = BackupSelectionDialog(
            app,
            {
                "conversations": 3,
                "codex": {
                    "name": "Codex chats, settings and attachments",
                    "path": "C:/Users/test/.codex",
                    "fileCount": 10,
                    "totalBytes": 100,
                    "locked": True,
                    "largestFolders": [],
                },
                "projects": [
                    {
                        "name": "DemoProject",
                        "path": "C:/Projects/DemoProject",
                        "sourcePresent": True,
                        "fileCount": 3,
                        "totalBytes": 70,
                        "largestFolders": [
                            {"name": ".git", "fileCount": 1, "totalBytes": 37}
                        ],
                    }
                ],
            },
        )
        app.update_idletasks()
        selection_default_complete = bool(
            selection_dialog.selected_summary
            == {"projects": 1, "files": 13, "bytes": 170}
            and not selection_dialog.excluded_paths
            and int(selection_dialog.tree.cget("height")) >= 20
            and selection_dialog.grab_current() is None
        )
        selection_dialog._select_none()
        selection_exclusion_visible = bool(
            selection_dialog.selected_summary
            == {"projects": 0, "files": 10, "bytes": 100}
            and selection_dialog.excluded_paths == ["C:/Projects/DemoProject"]
        )
        selection_dialog.destroy()
        portability_dialog = PathPortabilityDialog(
            app,
            {
                "summary": {
                    "translatedReferences": 3,
                    "excludedMachineStateReferences": 1,
                    "needsReviewReferences": 2,
                },
                "_localFindings": [{
                    "source": "sqlite",
                    "schemaField": "threads.future_workspace_path",
                    "classification": "needs-review",
                    "pathKind": "old-source-location",
                    "pathStatus": "missing",
                    "reason": "unrecognized-database-field",
                    "occurrences": 2,
                    "impact": "high",
                    "backupHandling": "preserved-unchanged",
                    "translationPlanned": False,
                    "dataIncluded": True,
                    "localPaths": [r"C:\Users\Source\OldProject"],
                }],
            },
        )
        app.update_idletasks()
        portability_dialog_created = bool(
            portability_dialog.winfo_exists() == 1
            and len(portability_dialog.tree.get_children()) == 1
            and "threads.future_workspace_path"
            in portability_dialog.detail_label.cget("text")
            and "%OLD_COMPUTER_PATH%" in portability_dialog.detail_label.cget("text")
        )
        portability_dialog.show_paths.set(True)
        portability_dialog._show_details()
        portability_local_toggle = "Source" in portability_dialog.detail_label.cget("text")
        portability_dialog.destroy()
        recovery_dialog = RecoveryDialog(
            app,
            {
                "validPoints": 0, "invalidPoints": 0, "totalBytes": 0,
                "keep": 2, "points": [],
            },
        )
        app.update_idletasks()
        recovery_dialog_created = bool(
            recovery_dialog.winfo_exists() == 1
            and recovery_dialog.empty_state is not None
            and any(
                child.cget("text") == app.t("recovery_empty_title")
                for child in recovery_dialog.empty_state.winfo_children()
            )
            and recovery_dialog.clean_button.instate(["disabled"])
        )
        recovery_dialog.destroy()
        diagnostics_dialog = DiagnosticsDialog(
            app,
            {
                "createdAtUtc": "2026-08-24T12:00:00+00:00",
                "summary": {"overall": "ready", "passed": 1, "notices": 0, "failed": 0},
                "checks": [{
                    "id": "windows", "status": "pass",
                    "summary": "Windows 11 detected.",
                    "facts": {"release": "11", "architecture": "AMD64"},
                }],
            },
        )
        app.update_idletasks()
        diagnostics_dialog_created = bool(
            diagnostics_dialog.winfo_exists() == 1
            and len(diagnostics_dialog.tree.get_children()) == 1
        )
        diagnostics_dialog.destroy()
        return bool(
            dutch and english and progress_ui_stable and navigation_tabs
            and len(app.action_buttons) == 6
            and blocked_is_disabled and ready_is_enabled
            and decision_button_enabled and decision_resolved
            and archive_button_enabled and project_decision_resolved
            and result_dialog_created and recovery_dialog_created
            and diagnostics_dialog_created
            and selection_default_complete and selection_exclusion_visible
            and portability_dialog_created and portability_local_toggle
        )
    finally:
        app.destroy()


def _portable_path_model_test() -> bool:
    source_profile = r"C:\Users\SourceUser"
    source_known = {
        "desktop": r"C:\Users\SourceUser\Desktop",
        "documents": r"D:\OneDrive\SourceUser\Documents",
        "downloads": r"C:\Users\SourceUser\Downloads",
    }
    target_known = {
        "desktop": r"C:\Users\TargetUser\Desktop",
        "documents": r"C:\Users\TargetUser\Documents",
        "downloads": r"C:\Users\TargetUser\Downloads",
    }
    documents = path_model.describe_location(
        r"D:\OneDrive\SourceUser\Documents\Example", source_profile, source_known
    )
    profile = path_model.describe_location(
        r"C:\Users\SourceUser\work\Example", source_profile, source_known
    )
    external = path_model.describe_location(
        r"C:\git\Example", source_profile, source_known
    )
    unc = path_model.describe_location(
        r"\\server\share\Example", source_profile, source_known
    )
    resolved_documents = path_model.resolve_portable_location(
        documents, r"C:\Users\TargetUser", target_known
    )
    resolved_profile = path_model.resolve_portable_location(
        profile, r"C:\Users\TargetUser", target_known
    )
    unresolved_external = path_model.resolve_portable_location(
        external, r"C:\Users\TargetUser", target_known
    )
    resolved_external = path_model.resolve_portable_location(
        external,
        r"C:\Users\TargetUser",
        target_known,
        {external["rootId"]: r"D:\Development"},
    )
    return bool(
        documents["kind"] == "known-folder"
        and documents["knownFolder"] == "documents"
        and path_model.suggested_target_expression(documents)
        == r"%DOCUMENTS%\Example"
        and str(resolved_documents) == r"C:\Users\TargetUser\Documents\Example"
        and profile["kind"] == "profile"
        and str(resolved_profile) == r"C:\Users\TargetUser\work\Example"
        and external["kind"] == "external-root"
        and external["requiresTargetMapping"] is True
        and unresolved_external is None
        and str(resolved_external) == r"D:\Development\Example"
        and unc["kind"] == "external-root"
        and not any(
            path_model.validate_location(item)
            for item in (documents, profile, external, unc)
        )
    )


def _long_unicode_path_model_test() -> bool:
    source_profile = r"C:\Users\Søurce"
    target_profile = r"C:\Users\旅行者"
    source_known = {
        "documents": source_profile + r"\OneDrive\Documenten",
        "desktop": source_profile + r"\Desktop",
        "downloads": source_profile + r"\Downloads",
    }
    target_known = {
        "documents": target_profile + r"\Documents",
        "desktop": target_profile + r"\Desktop",
        "downloads": target_profile + r"\Downloads",
    }
    relative = "Website – café\\bronbestanden\\" + "zeer-lange-projectmap-" * 6 + "einde"
    original = source_known["documents"] + "\\" + relative
    location = path_model.describe_location(original, source_profile, source_known)
    resolved = path_model.resolve_portable_location(location, target_profile, target_known)
    return bool(
        location.get("kind") == "known-folder"
        and str(location.get("relativePath", "")).replace("/", "\\") == relative
        and str(resolved).casefold()
        == (target_known["documents"] + "\\" + relative).casefold()
        and not path_model.validate_location(location)
        and len(original) > 180
    )


def _low_disk_space_test() -> bool:
    estimated = 2 * 1024 * 1024 * 1024
    required = backup.required_backup_space(estimated)
    rejected = False
    try:
        backup.ensure_backup_space(estimated, required - 1)
    except backup.BackupError:
        rejected = True
    return bool(rejected and backup.ensure_backup_space(estimated, required) == required)


def _project_identity_model_test(root: Path) -> bool:
    fixture = root / "identity-fixture"
    first_path = fixture / "first" / "SameName"
    second_path = fixture / "second" / "SameName"
    moved_path = fixture / "moved" / "SameName"
    for path in (first_path, second_path, moved_path):
        path.mkdir(parents=True)
    registry = project_identity.empty_registry()
    first = project_identity.assign_identity(
        registry, first_path, "SameName", ["codex-project-a"]
    )
    second = project_identity.assign_identity(
        registry, second_path, "SameName", ["codex-project-b"]
    )
    manifest = {
        "identityVersion": project_identity.IDENTITY_MANIFEST_VERSION,
        "roots": [
            {
                "projectId": first["projectId"],
                "rootId": first["rootId"],
                "name": "SameName",
                "codexProjectIds": ["codex-project-a"],
            }
        ],
    }
    project_identity.register_restored_roots(
        registry, manifest, {first["rootId"]: moved_path}
    )
    moved = project_identity.assign_identity(
        registry, moved_path, "SameName", ["codex-project-a"]
    )
    return bool(
        first["projectId"] != second["projectId"]
        and first["rootId"] != second["rootId"]
        and moved["projectId"] == first["projectId"]
        and moved["rootId"] == first["rootId"]
        and not project_identity.validate_registry(registry)
        and not any(any(path.iterdir()) for path in (first_path, second_path, moved_path))
    )


def _project_inventory_analysis_test(root: Path) -> bool:
    fixture = root / "inventory-root-fixture"
    parent = fixture / "Parent"
    child = parent / "Nested"
    missing = fixture / "Missing"
    child.mkdir(parents=True)
    candidates = [
        {
            "sourcePath": str(parent),
            "origins": ["database.project_roots", "global-state.local-projects"],
            "codexProjectIds": ["parent-project"],
        },
        {
            "sourcePath": str(child),
            "origins": ["threads.cwd"],
            "codexProjectIds": [],
        },
        {
            "sourcePath": str(missing),
            "origins": ["database.project_roots"],
            "codexProjectIds": ["missing-project"],
        },
    ]
    original_reparse_check = backup.is_reparse_point
    try:
        backup.is_reparse_point = lambda path: path.name == "Nested"
        analysis = backup.analyze_project_candidates(candidates)
    finally:
        backup.is_reparse_point = original_reparse_check
    return bool(
        analysis.get("candidateCount") == 3
        and analysis.get("nestedRoots")
        == [{"parentPath": str(parent), "childPath": str(child)}]
        and analysis.get("overlappingRoots") == analysis.get("nestedRoots")
        and analysis.get("missingRoots") == [str(missing)]
        and analysis.get("reparsePointRoots") == [str(child)]
        and analysis.get("multiSourceRoots")
        == [
            {
                "path": str(parent),
                "origins": [
                    "database.project_roots",
                    "global-state.local-projects",
                ],
            }
        ]
        and analysis.get("duplicateRoots") == analysis.get("multiSourceRoots")
    )


def _attachment_resilience_test(root: Path) -> bool:
    fixture = root / "attachment-resilience"
    package_root = fixture / "package"
    session = package_root / "codex" / "sessions" / "rollout-attachment-test.jsonl"
    source_profile = fixture / "source-user"
    attachment = source_profile / "AppData" / "Local" / "Temp" / "codex-denied.png"
    probe_denied = source_profile / "AppData" / "Local" / "Temp" / "codex-probe-denied.png"
    tool_only = source_profile / "AppData" / "Local" / "Temp" / "codex-tool-only.png"
    attachment.parent.mkdir(parents=True)
    session.parent.mkdir(parents=True)
    attachment.write_bytes(b"denied-during-copy")
    probe_denied.write_bytes(b"denied-during-probe")
    tool_only.write_bytes(b"tool-output-only")
    thread_id = "attachment-resilience-thread"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": thread_id, "cwd": str(source_profile)},
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": f"Another attached image: {probe_denied}",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": f"Attached image: {attachment}",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "input": f"Diagnostic output mentioned {tool_only}",
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    references = backup.find_attachment_paths([session])
    warnings: list[str] = []
    original_copy_file = backup.copy_file
    original_attachment_probe = backup.attachment_source_is_file

    def deny_attachment_copy(source: Path, destination: Path) -> None:
        if source.resolve(strict=False) == attachment.resolve(strict=False):
            raise PermissionError(13, "permission denied by self-test", str(source))
        original_copy_file(source, destination)

    def deny_attachment_probe(source: Path) -> bool:
        if source.resolve(strict=False) == probe_denied.resolve(strict=False):
            raise PermissionError(5, "access denied by self-test", str(source))
        return original_attachment_probe(source)

    try:
        backup.copy_file = deny_attachment_copy
        backup.attachment_source_is_file = deny_attachment_probe
        copied, unavailable = backup.copy_attachments(
            package_root,
            True,
            warnings,
            source_profile,
            {"documents": str(source_profile / "Documents")},
        )
    finally:
        backup.copy_file = original_copy_file
        backup.attachment_source_is_file = original_attachment_probe
    return bool(
        set(references) == {str(attachment), str(probe_denied)}
        and references[str(attachment)] == {thread_id}
        and not copied
        and len(unavailable) == 2
        and all(item.get("sourcePresent") is False for item in unavailable)
        and all(item.get("sourceStatus") == "unreadable" for item in unavailable)
        and sum("unreadable" in item for item in warnings) == 2
        and all(
            not (package_root / item["backupRelativePath"]).exists()
            for item in unavailable
        )
    )


def _plugin_runtime_policy_test(root: Path) -> bool:
    fixture = root / "plugin-runtime-policy"
    source_codex = fixture / "source-user" / ".codex"
    package_root = fixture / "package"
    target_codex = fixture / "target-user" / ".codex"
    plugin_source = source_codex / "plugins" / "cache" / "locked-plugin.bin"
    skill_source = source_codex / "skills" / "demo" / "SKILL.md"
    plugin_source.parent.mkdir(parents=True)
    skill_source.parent.mkdir(parents=True)
    plugin_source.write_bytes(b"machine-specific-plugin-runtime")
    skill_source.write_text("# Portable skill\n", encoding="utf-8")
    (source_codex / "config.toml").write_text(
        "[plugins]\nenabled = true\n", encoding="utf-8"
    )

    original_copy_tree = backup.copy_tree

    def reject_plugin_copy(
        source: Path,
        destination: Path,
        exclude_fragments: list[str],
        warnings: list[str],
        skipped_reconstructable_cache: list[dict[str, Any]] | None = None,
    ) -> tuple[int, int]:
        if source.name.lower() == "plugins":
            raise PermissionError(87, "plugin runtime must not be opened", str(source))
        return original_copy_tree(
            source,
            destination,
            exclude_fragments,
            warnings,
            skipped_reconstructable_cache,
        )

    warnings: list[str] = []
    try:
        backup.copy_tree = reject_plugin_copy
        stats_files, _stats_bytes, stats_details = backup._portable_profile_stats(
            source_codex
        )
        records = backup.copy_portable_codex_profile(
            source_codex, package_root, warnings
        )
    finally:
        backup.copy_tree = original_copy_tree

    legacy_plugins = package_root / "codex" / "portable-profile" / "plugins"
    (legacy_plugins / "cache").mkdir(parents=True)
    (legacy_plugins / "cache" / "legacy-plugin.bin").write_bytes(b"legacy")
    target_plugin = target_codex / "plugins" / "cache" / "target-plugin.bin"
    target_plugin.parent.mkdir(parents=True)
    target_plugin.write_bytes(b"keep-target-runtime")

    class IdentityTranslator:
        @staticmethod
        def text(value: str) -> str:
            return value

    restored = restore._restore_portable_profile(
        package_root, target_codex, IdentityTranslator()
    )
    record_names = {str(item.get("name", "")).lower() for item in records}
    detail_names = {str(item.get("name", "")).lower() for item in stats_details}
    return bool(
        stats_files == 2
        and "plugins" not in record_names
        and "plugins" not in detail_names
        and {"config.toml", "skills"}.issubset(record_names)
        and not (target_codex / "plugins" / "cache" / "legacy-plugin.bin").exists()
        and target_plugin.read_bytes() == b"keep-target-runtime"
        and (target_codex / "config.toml").is_file()
        and (target_codex / "skills" / "demo" / "SKILL.md").is_file()
        and restored == 2
        and not warnings
    )


def _lineage_model_test() -> bool:
    digest_a = "a" * 64
    digest_b = "b" * 64
    digest_c = "c" * 64
    base = {
        "same": digest_a,
        "change": digest_a,
        "remove": digest_a,
        "conflict": digest_a,
    }
    current = {
        "same": {"key": "same", "kind": "test", "fingerprint": digest_a},
        "change": {"key": "change", "kind": "test", "fingerprint": digest_b},
        "new": {"key": "new", "kind": "test", "fingerprint": digest_c},
        "conflict": {"key": "conflict", "kind": "test", "fingerprint": digest_b},
    }
    peer = {
        "same": digest_a,
        "change": digest_a,
        "remove": digest_a,
        "conflict": digest_c,
    }
    classified = {
        item["key"]: item["state"]
        for item in lineage.classify_items(current, base, peer)
    }
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    third_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    first = lineage.build_manifest(
        first_id, device_id, "2026-08-23T00:00:00Z", current,
        lineage.empty_state(), None,
    )
    second = lineage.build_manifest(
        second_id, device_id, "2026-08-23T00:01:00Z", current,
        lineage.state_from_manifest(first), None,
    )
    third = lineage.build_manifest(
        third_id, device_id, "2026-08-23T00:02:00Z", current,
        lineage.state_from_manifest(second), None,
    )
    return bool(
        classified
        == {
            "change": "changed",
            "conflict": "independentlyChanged",
            "new": "new",
            "remove": "removed",
            "same": "unchanged",
        }
        and first["parentBackupId"] is None
        and first["relation"] == "root"
        and second["parentBackupId"] == first_id
        and second["relation"] == "linear"
        and third["parentBackupId"] == second_id
        and third["relation"] == "linear"
        and not lineage.validate_manifest(first)
        and not lineage.validate_manifest(second)
        and not lineage.validate_manifest(third)
    )


def _streaming_lineage_digest_test(root: Path) -> bool:
    fixture = root / "streaming-lineage"
    fixture.mkdir()
    source_profile = r"C:\Users\SourceUser"
    attachment = rf"{source_profile}\AppData\Local\Temp\codex-image.png"
    replacements = [
        (
            rf"{source_profile}\AppData\Local\Temp\codex-image-{index:04d}.png",
            f"%ATTACHMENT:codex-image-{index:04d}.png%",
        )
        for index in range(700)
    ] + [
        (attachment, "%ATTACHMENT:codex-image.png%"),
        (source_profile, "%PROFILE%"),
    ]
    small = fixture / "small.jsonl"
    small_value = {"message": attachment, "profile": source_profile}
    small.write_text(json.dumps(small_value) + "\r\n", encoding="utf-8")
    expected_small_text = (
        json.dumps(
            {
                "message": "%ATTACHMENT:codex-image.png%",
                "profile": "%PROFILE%",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    small_progress: list[int] = []
    small_digest = lineage.semantic_file_digest(
        small, replacements, small_progress.append
    )

    large = fixture / "large.jsonl"
    large_text = json.dumps(
        {"path": source_profile, "blob": "A" * (2 * 1024 * 1024 + 100)}
    )
    large.write_text(large_text + "\n", encoding="utf-8")
    expected_large = (
        large_text.replace(source_profile, "%PROFILE%") + "\n"
    ).encode("utf-8")
    large_progress: list[int] = []
    large_digest = lineage.semantic_file_digest(
        large, replacements, large_progress.append
    )
    return bool(
        small_digest
        == hashlib.sha256(expected_small_text.encode("utf-8")).hexdigest()
        and sum(small_progress) == small.stat().st_size
        and large_digest == hashlib.sha256(expected_large).hexdigest()
        and sum(large_progress) == large.stat().st_size
        and all(
            lineage._replace_paths(original, replacements) == token
            for original, token in replacements[:-1]
        )
    )


def _location_mapper_model_test(root: Path) -> bool:
    target_profile = root / "mapper-target-user"
    (target_profile / "Documents").mkdir(parents=True)
    package_root = root / "mapper-package"
    package_root.mkdir()
    source_profile = r"C:\Users\SourceUser"
    known_location = path_model.describe_location(
        r"C:\Users\SourceUser\Documents\KnownProject",
        source_profile,
        {"documents": r"C:\Users\SourceUser\Documents"},
    )
    external_location = path_model.describe_location(
        r"D:\Development\ExternalProject", source_profile, {}
    )
    external_root_id = str(external_location["rootId"])
    mappings = [
        {
            "id": "known-root",
            "originalPath": known_location["originalPath"],
            "sourcePresent": True,
            "location": known_location,
        },
        {
            "id": "external-root",
            "originalPath": external_location["originalPath"],
            "sourcePresent": True,
            "location": external_location,
        },
    ]
    unresolved = location_mapper.build_plan(mappings, target_profile, {}, package_root)
    selected_root = target_profile / "Mapped external root"
    mapped = location_mapper.build_plan(
        mappings, target_profile, {external_root_id: str(selected_root)}, package_root
    )
    unsafe = location_mapper.build_plan(
        mappings, target_profile, {external_root_id: str(target_profile)}, package_root
    )
    colliding = location_mapper.build_plan(
        mappings + [{**mappings[1], "id": "external-root-copy"}],
        target_profile,
        {external_root_id: str(selected_root)},
        package_root,
    )
    registry_path = root / "mapper-state" / "location-mappings.json"
    registry = location_mapper.empty_registry()
    location_mapper.remember_external_roots(
        registry, {external_root_id: str(selected_root)}, "2026-08-23T00:00:00Z"
    )
    location_mapper.save_registry(registry_path, registry)
    loaded = location_mapper.load_registry(registry_path)
    mapped_targets = {item["id"]: item["targetPath"] for item in mapped["items"]}
    manifest = package_root / "manifest"
    manifest.mkdir()
    backup.write_json(
        manifest / "package.json",
        {
            "source": {
                "profilePath": source_profile,
                "knownFolders": {"documents": rf"{source_profile}\Documents"},
            }
        },
    )
    backup.write_json(
        manifest / "path-mappings.json",
        {"mappingVersion": 2, "projects": mappings, "attachments": []},
    )
    missing_mapping_blocked = False
    try:
        restore.PathTranslator(package_root, target_profile)
    except restore.RestoreError:
        missing_mapping_blocked = True
    translator = restore.PathTranslator(
        package_root, target_profile, {external_root_id: str(selected_root)}
    )
    codex_tree = location_mapper.validate_external_root(
        target_profile / ".codex" / "projects", target_profile, package_root
    )
    profile_parent = location_mapper.validate_external_root(
        target_profile.parent, target_profile, package_root
    )
    return bool(
        not unresolved["ready"]
        and len(unresolved["requiredExternalRoots"]) == 1
        and mapped["ready"]
        and Path(mapped_targets["known-root"])
        == target_profile / "Documents" / "KnownProject"
        and Path(mapped_targets["external-root"])
        == selected_root / "ExternalProject"
        and not unsafe["ready"]
        and unsafe["issues"]
        and not colliding["ready"]
        and any("collides" in item["error"] for item in colliding["issues"])
        and location_mapper.external_roots(loaded)[external_root_id]
        == str(selected_root.resolve(strict=False))
        and missing_mapping_blocked
        and translator.project_targets["external-root"]
        == selected_root / "ExternalProject"
        and codex_tree
        and profile_parent
    )


def _path_portability_audit_test(root: Path) -> bool:
    profile = root / "portability-audit-user"
    codex = profile / ".codex"
    project = profile / "Documents" / "AuditProject"
    codex.mkdir(parents=True)
    project.mkdir(parents=True)
    extended_project = "\\\\?\\" + str(project)
    state = {
        "local-projects": {
            "audit-project": {"rootPaths": [str(project)]}
        },
        "future-machine-location": {
            "path": r"Z:\FutureMachine\PrivateWorkspace"
        },
        "electron-persisted-atom-state": {
            "history": "https://github.com/example/repository and D:\\, ordinary prose"
        },
    }
    (codex / ".codex-global-state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    database = sqlite3.connect(codex / "state_5.sqlite")
    database.executescript(
        """
        CREATE TABLE project_roots (
          project_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT NOT NULL
        );
        CREATE TABLE threads (
          id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL, cwd TEXT NOT NULL,
          future_workspace_path TEXT
        );
        """
    )
    database.execute(
        "INSERT INTO project_roots VALUES(?,?,?)",
        ("audit-project", 0, extended_project),
    )
    database.execute(
        "INSERT INTO threads VALUES(?,?,?,?)",
        (
            "audit-thread",
            str(codex / "sessions" / "audit.jsonl"),
            str(project),
            r"Y:\UnknownDevice\FutureProject",
        ),
    )
    database.commit()
    database.close()
    before = _hash_tree(profile)
    result = portability_audit.audit(profile, codex)
    local_result = portability_audit.audit(
        profile, codex, include_local_details=True
    )
    restored_result = portability_audit.audit(
        profile, codex, legacy_roots=[r"Y:\UnknownDevice"]
    )
    after = _hash_tree(profile)
    serialized = json.dumps(result, ensure_ascii=False)
    summary = result.get("summary") or {}
    findings = result.get("findings") or []
    return bool(
        before == after
        and result.get("status") == "attention"
        and summary.get("translatedReferences", 0) >= 3
        and summary.get("needsReviewReferences", 0) >= 2
        and summary.get("unrecognizedSchemaFields", 0) == 2
        and result.get("privacy", {}).get("containsPathValues") is False
        and result.get("privacy", {}).get("unknownFieldNamesAreFingerprinted") is True
        and str(profile).lower() not in serialized.lower()
        and "FutureMachine".lower() not in serialized.lower()
        and "UnknownDevice".lower() not in serialized.lower()
        and "electron-persisted-atom-state" not in serialized
        and all("unrecognized-field-" in item.get("schemaField", "")
                for item in findings if item.get("reason", "").startswith("unrecognized-"))
        and any(
            item.get("schemaField") == "threads.future_workspace_path"
            and item.get("backupHandling") == "preserved-unchanged"
            and item.get("dataIncluded") is True
            and item.get("localPaths")
            for item in local_result.get("_localFindings", [])
        )
        and "_localFindings" not in result
        and any(
            item.get("schemaField") == "project_roots.path"
            and item.get("pathStatus") == "present"
            and any(
                str(path).startswith("\\\\?\\")
                for path in item.get("localPaths", [])
            )
            for item in local_result.get("_localFindings", [])
        )
        and restored_result.get("summary", {}).get("oldSourceReferences", 0) >= 1
        and any(
            item.get("pathKind") == "old-source-location"
            and item.get("impact") == "high"
            for item in restored_result.get("findings", [])
        )
    )


def _run_test_git(root: Path, *arguments: str) -> bool:
    executable = shutil.which("git")
    if not executable:
        return False
    completed = subprocess.run(
        [executable, "-C", str(root), *arguments],
        capture_output=True,
        timeout=10,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.returncode == 0


def _git_conflict_insight_test(root: Path) -> tuple[bool, bool]:
    source = root / "git-insight-source"
    target = root / "git-insight-target"
    later_target = root / "git-insight-later-target"
    dirty_target = root / "git-insight-dirty-target"
    source.mkdir(parents=True)
    if not shutil.which("git"):
        fallback = git_insight.compare_repositories(source, target)
        return (
            fallback.get("classification") == "insufficient-evidence",
            fallback.get("automaticActionChanged") is False,
        )
    if not _run_test_git(source, "init"):
        return False, False
    for key, value in (("user.email", "lifeboat@example.invalid"), ("user.name", "Lifeboat Test")):
        if not _run_test_git(source, "config", key, value):
            return False, False
    (source / "state.txt").write_text("base\n", encoding="utf-8")
    if not (_run_test_git(source, "add", "state.txt") and _run_test_git(source, "commit", "-m", "base")):
        return False, False
    executable = str(shutil.which("git"))
    for destination in (target,):
        completed = subprocess.run(
            [executable, "clone", "--quiet", str(source), str(destination)],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            return False, False
    (source / "state.txt").write_text("backup ahead\n", encoding="utf-8")
    if not (_run_test_git(source, "add", "state.txt") and _run_test_git(source, "commit", "-m", "backup ahead")):
        return False, False
    backup_ahead = git_insight.compare_repositories(source, target)
    for destination in (later_target, dirty_target):
        completed = subprocess.run(
            [executable, "clone", "--quiet", str(source), str(destination)],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            return False, False
    for repository in (target, later_target, dirty_target):
        _run_test_git(repository, "config", "user.email", "lifeboat@example.invalid")
        _run_test_git(repository, "config", "user.name", "Lifeboat Test")
    (target / "target.txt").write_text("diverged\n", encoding="utf-8")
    if not (_run_test_git(target, "add", "target.txt") and _run_test_git(target, "commit", "-m", "diverged")):
        return False, False
    diverged = git_insight.compare_repositories(source, target)
    (later_target / "later.txt").write_text("computer ahead\n", encoding="utf-8")
    if not (_run_test_git(later_target, "add", "later.txt") and _run_test_git(later_target, "commit", "-m", "computer ahead")):
        return False, False
    computer_ahead = git_insight.compare_repositories(source, later_target)
    (dirty_target / "untracked.txt").write_text("local only\n", encoding="utf-8")
    dirty = git_insight.compare_repositories(source, dirty_target)
    serialized = json.dumps((backup_ahead, diverged, computer_ahead, dirty))
    explanations = bool(
        backup_ahead.get("historyRelation") == "backup-ahead"
        and diverged.get("historyRelation") == "diverged"
        and diverged.get("classification") == "true-divergence"
        and computer_ahead.get("historyRelation") == "computer-ahead"
        and dirty.get("historyRelation") == "same-commit"
        and dirty.get("classification") == "same-commit-working-tree-differs"
        and str(source) not in serialized
        and str(target) not in serialized
    )
    advisory_only = all(
        item.get("automaticActionChanged") is False
        for item in (backup_ahead, diverged, computer_ahead, dirty)
    )
    return explanations, advisory_only


def _atomic_metadata_test(root: Path) -> bool:
    folder = root / "atomic-metadata"
    target = folder / "state.json"
    atomic_io.write_json(target, {"generation": "old"})
    interrupted = False
    try:
        with mock.patch.object(atomic_io.os, "replace", side_effect=OSError("injected interruption")):
            atomic_io.write_json(target, {"generation": "partial"})
    except OSError:
        interrupted = True
    old_survived = backup.read_json(target) == {"generation": "old"}
    no_partial = not list(folder.glob(".*.tmp"))
    atomic_io.write_json(target, {"generation": "new"})
    writers = folder / "writers"
    backup.write_json(writers / "manifest.json", {"valid": True})
    lineage.save_state(writers / "lineage.json", lineage.empty_state())
    project_identity.save_registry(
        writers / "projects.json", project_identity.empty_registry()
    )
    location_mapper.save_registry(
        writers / "locations.json", location_mapper.empty_registry()
    )
    diagnostics.save_report(writers / "diagnostics.json", {"safe": True})
    return bool(
        interrupted
        and old_survived
        and no_partial
        and backup.read_json(target) == {"generation": "new"}
        and all(backup.read_json(path) is not None for path in writers.glob("*.json"))
        and not list(folder.rglob(".*.tmp"))
    )


def _conversation_prefix_classifier_test(root: Path) -> tuple[bool, bool]:
    folder = root / "conversation-prefix-classifier"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "source.jsonl"
    target = folder / "target.jsonl"
    source_profile = r"C:\Users\Source"
    target_profile = r"C:\Users\Target"
    records = [
        {
            "type": "session_meta",
            "payload": {"id": "prefix-thread", "cwd": source_profile + r"\Project"},
        },
        {"type": "event_msg", "payload": {"message": "unchanged"}},
        {"type": "event_msg", "payload": {"message": "incoming tail"}},
    ]
    source.write_text(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in records),
        encoding="utf-8",
    )
    target_records = json.loads(json.dumps(records[:2]))
    target_records[0]["payload"]["cwd"] = target_profile + r"\Project"
    target.write_text(
        "".join(
            json.dumps(item, separators=(",", ":")) + "\n"
            for item in target_records
        ),
        encoding="utf-8",
    )
    source_replacements = [(source_profile, "%PROFILE%")]
    target_replacements = [(target_profile, "%PROFILE%")]
    metadata = {
        "title": "Prefix test",
        "archived": False,
        "pinned": False,
        "projectless": True,
        "projectId": None,
        "historyMode": "full",
        "memoryMode": "local",
    }
    before = (backup.sha256_file(source), backup.sha256_file(target))
    safe = conversation_prefix.compare(
        source,
        target,
        source_replacements,
        target_replacements,
        metadata,
        dict(metadata),
    )
    after = (backup.sha256_file(source), backup.sha256_file(target))
    safe_classifier = bool(
        safe.get("automatic")
        and safe.get("relation") == "target-prefix"
        and safe.get("matchedRecords") == 2
        and safe.get("additionalSourceRecords") == 1
        and before == after
    )

    changed = json.loads(json.dumps(target_records))
    changed[1]["payload"]["message"] = "edited locally"
    target.write_text(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in changed),
        encoding="utf-8",
    )
    diverged = conversation_prefix.compare(
        source,
        target,
        source_replacements,
        target_replacements,
        metadata,
        metadata,
    )
    metadata_changed = dict(metadata)
    metadata_changed["archived"] = True
    metadata_conflict = conversation_prefix.compare(
        source,
        target,
        source_replacements,
        target_replacements,
        metadata,
        metadata_changed,
    )
    target.write_text('{"type":"broken"\n', encoding="utf-8")
    invalid = conversation_prefix.compare(
        source,
        target,
        source_replacements,
        target_replacements,
        metadata,
        metadata,
    )
    strict_rejection = bool(
        not diverged.get("automatic")
        and diverged.get("relation") == "diverged"
        and not metadata_conflict.get("automatic")
        and metadata_conflict.get("relation") == "metadata-conflict"
        and not invalid.get("automatic")
        and invalid.get("relation") == "invalid"
    )
    return safe_classifier, strict_rejection


def _rollout_preflight_diagnostics_test(root: Path, source_profile: Path) -> bool:
    duplicate_profile = root / "duplicate-rollout-user"
    _copy_profile_fixture(source_profile, duplicate_profile)
    duplicate_codex = duplicate_profile / ".codex"
    connection = sqlite3.connect(duplicate_codex / "state_5.sqlite")
    try:
        database_rollout = Path(
            str(
                connection.execute(
                    'SELECT "rollout_path" FROM "threads" WHERE "id"=?',
                    (THREAD_ID,),
                ).fetchone()[0]
            ).replace("\\\\?\\", "")
        )
    finally:
        connection.close()
    duplicate_rollout = (
        duplicate_codex
        / "archived_sessions"
        / f"duplicate-{THREAD_ID}.jsonl"
    )
    duplicate_rollout.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_rollout, duplicate_rollout)
    unmatched_database_rollout = duplicate_codex / "sessions" / "missing-rollout.jsonl"
    connection = sqlite3.connect(duplicate_codex / "state_5.sqlite")
    try:
        connection.execute(
            'UPDATE "threads" SET "rollout_path"=? WHERE "id"=?',
            (str(unmatched_database_rollout), THREAD_ID),
        )
        connection.commit()
    finally:
        connection.close()
    source_before = _hash_tree(duplicate_profile)

    destination = root / "duplicate-rollout-usb"
    config = root / "duplicate-rollout-config.json"
    backup.write_json(
        config,
        {
            "configVersion": 1,
            "destinationRoot": str(destination),
            "includeAttachments": True,
            "projects": [],
            "additionalPortablePaths": [],
            "excludeDirectoryNames": [],
            "projectRegistryPath": str(root / "duplicate-state" / "project-registry.json"),
            "lineageStatePath": str(root / "duplicate-state" / "lineage-state.json"),
            "deviceStatePath": str(root / "duplicate-state" / "device.json"),
        },
    )
    portable_copy_called = False

    def reject_portable_copy(*_args, **_kwargs):
        nonlocal portable_copy_called
        portable_copy_called = True
        raise AssertionError("portable profile copy ran before rollout preflight")

    failure: Exception | None = None
    with mock.patch.object(
        backup, "copy_portable_codex_profile", side_effect=reject_portable_copy
    ):
        try:
            backup.build_backup(
                argparse.Namespace(
                    config=str(config),
                    destination=str(destination),
                    source_profile=str(duplicate_profile),
                    source_codex_home=str(duplicate_codex),
                    allow_running_test=True,
                )
            )
        except Exception as exc:
            failure = exc

    retained = [path for path in destination.iterdir() if path.is_dir()]
    report_path = retained[0] / "reports" / "rollout-errors.json" if retained else None
    report = backup.read_json(report_path) if report_path and report_path.is_file() else {}
    incomplete_path = retained[0] / "INCOMPLETE.json" if retained else None
    incomplete = (
        backup.read_json(incomplete_path)
        if incomplete_path and incomplete_path.is_file()
        else {}
    )
    duplicate_items = report.get("duplicateRollouts", [])
    candidates = duplicate_items[0].get("candidates", []) if duplicate_items else []
    candidate_paths = {str(item.get("sourcePath")) for item in candidates}
    hashes = {str(item.get("sha256")) for item in candidates}
    if retained:
        # Even a stale or misleading completion manifest must never make a
        # clearly marked staging directory discoverable as a restore source.
        backup.write_json(
            retained[0] / "manifest" / "package.json", {"backupComplete": True}
        )
    with mock.patch.object(windows, "removable_drives", return_value=[destination]):
        auto_detected = windows.detect_backup_packages()
    incomplete_validation = validate(retained[0], False) if retained else {}
    return bool(
        isinstance(failure, backup.BackupError)
        and THREAD_ID in str(failure)
        and str(database_rollout) in str(failure)
        and str(duplicate_rollout) in str(failure)
        and report_path is not None
        and str(report_path) in str(failure)
        and report.get("duplicateThreadIds") == [THREAD_ID]
        and report.get("missingThreadIds") == []
        and duplicate_items[0].get("candidateHashesMatch") is True
        and duplicate_items[0].get("databaseRolloutPath")
        == str(unmatched_database_rollout)
        and candidate_paths == {str(database_rollout), str(duplicate_rollout)}
        and len(hashes) == 1
        and None not in {item.get("sha256") for item in candidates}
        and sum(bool(item.get("matchesDatabaseRolloutPath")) for item in candidates) == 0
        and report.get("resolution", {}).get("unresolvedDuplicateThreadIds")
        == [THREAD_ID]
        and not portable_copy_called
        and not any(
            (path / "codex" / "portable-profile").exists() for path in retained
        )
        and len(retained) == 1
        and retained[0].name.startswith(backup.STAGING_NAME_PREFIX)
        and len(retained[0].name)
        == len(backup.STAGING_NAME_PREFIX) + backup.STAGING_TOKEN_LENGTH
        and incomplete.get("incomplete") is True
        and incomplete.get("restorable") is False
        and incomplete.get("phase") == "rollout-preflight"
        and "reports/backup-error.txt" in incomplete.get("availableReports", [])
        and "reports/rollout-errors.json" in incomplete.get("availableReports", [])
        and not windows.completed_backup_package(retained[0])
        and retained[0] not in auto_detected
        and incomplete_validation.get("valid") is False
        and any(
            "INCOMPLETE.json" in error
            for error in incomplete_validation.get("errors", [])
        )
        and source_before == _hash_tree(duplicate_profile)
    )


def _path_budget_test(root: Path) -> bool:
    source = root / "source" / "file.txt"
    destination = Path("C:/B")

    def boundary_report(
        length: int, long_paths: bool, source_path: Path = source
    ) -> dict[str, Any]:
        final_root = destination / "Codex-PortableBackup-YYYYMMDD-HHMMSS-000000"
        relative_length = length - len(str(final_root)) - 1
        if relative_length <= 0 or relative_length > backup.COMMON_COMPONENT_LIMIT:
            raise AssertionError("path-boundary fixture is not representable")
        budget = backup.new_path_budget()
        backup.record_projected_path(
            budget,
            source_path,
            "x" * relative_length,
            reconstructable_cache=backup.is_reconstructable_python_cache(source_path),
        )
        return backup.destination_path_budget(
            destination, backup.path_budget_items(budget), long_paths=long_paths
        )

    boundary_259 = boundary_report(259, False)
    boundary_260 = boundary_report(260, False)
    boundary_261 = boundary_report(261, False)
    boundary_261_long = boundary_report(261, True)
    cache_boundary_261 = boundary_report(
        261, False, source.with_name("reconstructable.pyc")
    )

    component_budget = backup.new_path_budget()
    oversized_component = "x" * (backup.COMMON_COMPONENT_LIMIT + 1)
    backup.record_projected_path(
        component_budget, source, f"codex/{oversized_component}/file.txt"
    )
    component_report = backup.destination_path_budget(
        root / "usb", backup.path_budget_items(component_budget), long_paths=True
    )

    preview = {
        "codex": {
            "pathBudgetItems": [
                {"sourcePath": "codex", "packageRelativePath": "codex/file.txt"}
            ]
        },
        "projects": [
            {
                "path": str(root / "included"),
                "pathBudgetItems": [
                    {
                        "sourcePath": "included",
                        "packageRelativePath": "projects/root-id/included.txt",
                    }
                ],
            },
            {
                "path": str(root / "excluded"),
                "pathBudgetItems": [
                    {
                        "sourcePath": "excluded",
                        "packageRelativePath": "projects/root-id/excluded.txt",
                    }
                ],
            },
        ],
    }
    selected_items = backup.preview_path_budget_items(
        preview, [str(root / "excluded")]
    )
    return bool(
        boundary_259["safe"]
        and boundary_259["longest"]["pathLength"] == 259
        and not boundary_260["safe"]
        and boundary_260["classicLimitExceeded"]
        and boundary_260["longest"]["pathLength"] == 260
        and not boundary_261["safe"]
        and boundary_261["classicLimitExceeded"]
        and boundary_261["longest"]["pathLength"] == 261
        and boundary_261_long["safe"]
        and cache_boundary_261["safe"]
        and cache_boundary_261["reconstructableCacheLimitExceeded"]
        .get("classicLimitExceeded")
        is True
        and not component_report["safe"]
        and component_report["componentLimitExceeded"]["componentLength"]
        == backup.COMMON_COMPONENT_LIMIT + 1
        and {item["sourcePath"] for item in selected_items}
        == {"codex", "included"}
    )


def _destination_prompt_test() -> bool:
    from . import gui

    initial = gui.backup_destination_initial_directory(
        [Path("F:/")], Path("C:/Users/Test/Documents")
    )
    with mock.patch.object(
        gui.filedialog, "askdirectory", return_value="F:\\B"
    ) as prompt:
        selected = gui.ask_backup_destination(None, "Choose", initial)
    call = prompt.call_args
    return bool(
        initial == str(Path("F:/") / "Codex Backups")
        and selected == "F:\\B"
        and prompt.call_count == 1
        and call.kwargs.get("initialdir") == initial
    )


def _reconstructable_cache_policy_test(
    root: Path, source_profile: Path
) -> tuple[bool, bool]:
    profile = root / "python-cache-user"
    _copy_profile_fixture(source_profile, profile)
    codex = profile / ".codex"
    project = profile / "Documents" / "DemoProject"
    cache_files = [
        project / "standalone-cache.pyc",
        project / "standalone-cache.pyo",
        project / "__pycache__" / "generated.cache",
    ]
    for index, path in enumerate(cache_files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"reconstructable-{index}".encode("ascii"))
    source_before = _hash_tree(profile)
    destination = root / "python-cache-usb"
    config = root / "python-cache-config.json"
    backup.write_json(
        config,
        {
            "configVersion": 1,
            "destinationRoot": str(destination),
            "includeAttachments": True,
            "projects": [{"path": str(project), "required": True}],
            "additionalPortablePaths": [],
            "excludeDirectoryNames": [],
            "projectRegistryPath": str(
                root / "python-cache-state" / "project-registry.json"
            ),
            "lineageStatePath": str(
                root / "python-cache-state" / "lineage-state.json"
            ),
            "deviceStatePath": str(root / "python-cache-state" / "device.json"),
        },
    )
    original_copy_file = backup.copy_file
    cache_keys = {backup.normalized_source_key(path) for path in cache_files}

    def fail_cache_copy(source: Path, destination_path: Path) -> None:
        if backup.normalized_source_key(source) in cache_keys:
            raise PermissionError(13, "cache file is locked", str(source))
        original_copy_file(source, destination_path)

    with mock.patch.object(backup, "copy_file", side_effect=fail_cache_copy):
        package = backup.build_backup(
            argparse.Namespace(
                config=str(config),
                destination=str(destination),
                source_profile=str(profile),
                source_codex_home=str(codex),
                allow_running_test=True,
            )
        )

    cache_report = backup.read_json(
        package / "reports" / "skipped-python-cache.json"
    )
    package_manifest = backup.read_json(package / "manifest" / "package.json")
    backup_report = backup.read_json(package / "reports" / "backup-report.json")
    from .gui import _backup_result_model

    result_model = _backup_result_model(package, validate(package, False))
    reported_sources = {
        str(item.get("sourcePath")) for item in cache_report.get("items", [])
    }
    cache_warning_complete = bool(
        cache_report.get("count") == len(cache_files)
        and reported_sources == {str(path) for path in cache_files}
        and all(item.get("errorType") == "PermissionError" for item in cache_report["items"])
        and package_manifest.get("backupComplete") is True
        and package_manifest.get("counts", {}).get(
            "skippedReconstructablePythonCache"
        )
        == len(cache_files)
        and package_manifest.get("skippedReconstructablePythonCache", {}).get(
            "reportRelativePath"
        )
        == "reports/skipped-python-cache.json"
        and backup_report.get("skippedReconstructablePythonCache", {}).get("count")
        == len(cache_files)
        and result_model.get("valid") is True
        and result_model.get("warningCount", 0) >= len(cache_files)
        and result_model.get("warnings", {}).get("pythonCache") == len(cache_files)
        and not (package / "INCOMPLETE.json").exists()
        and source_before == _hash_tree(profile)
    )
    (package / "reports" / "skipped-python-cache.json").unlink()
    missing_cache_report_rejected = not validate(package, False).get("valid")
    cache_warning_complete = bool(
        cache_warning_complete and missing_cache_report_rejected
    )

    strict_source = root / "mandatory-copy-source"
    strict_destination = root / "mandatory-copy-destination"
    strict_source.mkdir(parents=True)
    mandatory_file = strict_source / "important-source.py"
    mandatory_file.write_text("print('must be copied')\n", encoding="utf-8")
    skipped: list[dict[str, Any]] = []
    warnings: list[str] = []

    def fail_mandatory_copy(_source: Path, _destination: Path) -> None:
        raise PermissionError(13, "normal source file is locked", str(mandatory_file))

    mandatory_failure: Exception | None = None
    with mock.patch.object(backup, "copy_file", side_effect=fail_mandatory_copy):
        try:
            backup.copy_tree(
                strict_source,
                strict_destination,
                [],
                warnings,
                skipped,
            )
        except Exception as exc:
            mandatory_failure = exc
    mandatory_stays_strict = bool(
        isinstance(mandatory_failure, backup.BackupError)
        and str(mandatory_file) in str(mandatory_failure)
        and not skipped
        and not warnings
    )
    return cache_warning_complete, mandatory_stays_strict


def _rollout_resolution_test(
    root: Path, source_profile: Path
) -> tuple[bool, bool]:
    results: list[bool] = []
    for label, divergent in (("identical", False), ("different", True)):
        profile = root / f"resolved-{label}-rollout-user"
        _copy_profile_fixture(source_profile, profile)
        codex = profile / ".codex"
        connection = sqlite3.connect(codex / "state_5.sqlite")
        try:
            canonical_source = Path(
                str(
                    connection.execute(
                        'SELECT "rollout_path" FROM "threads" WHERE "id"=?',
                        (THREAD_ID,),
                    ).fetchone()[0]
                ).replace("\\\\?\\", "")
            )
        finally:
            connection.close()
        duplicate_source = (
            codex / "archived_sessions" / f"duplicate-{label}-{THREAD_ID}.jsonl"
        )
        duplicate_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_source, duplicate_source)
        if divergent:
            with duplicate_source.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": "2026-09-14T08:00:00Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "user_message",
                                "message": "non-canonical divergent copy",
                            },
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        source_before = _hash_tree(profile)
        destination = root / f"resolved-{label}-rollout-usb"
        config = root / f"resolved-{label}-rollout-config.json"
        backup.write_json(
            config,
            {
                "configVersion": 1,
                "destinationRoot": str(destination),
                "includeAttachments": True,
                "projects": [],
                "additionalPortablePaths": [],
                "excludeDirectoryNames": [],
                "projectRegistryPath": str(
                    root / f"resolved-{label}-state" / "project-registry.json"
                ),
                "lineageStatePath": str(
                    root / f"resolved-{label}-state" / "lineage-state.json"
                ),
                "deviceStatePath": str(
                    root / f"resolved-{label}-state" / "device.json"
                ),
            },
        )
        package = backup.build_backup(
            argparse.Namespace(
                config=str(config),
                destination=str(destination),
                source_profile=str(profile),
                source_codex_home=str(codex),
                allow_running_test=True,
            )
        )
        resolution_report = backup.read_json(
            package / "reports" / "rollout-resolution.json"
        )
        resolution = resolution_report.get("resolution", {})
        resolved = resolution.get("resolved", [])
        preserved = resolved[0].get("preservedNonCanonical", []) if resolved else []
        preserved_relative = (
            str(preserved[0].get("preservedBackupRelativePath"))
            if preserved
            else ""
        )
        canonical_relative = (
            "codex/" + canonical_source.relative_to(codex).as_posix()
        )
        duplicate_relative = "codex/" + duplicate_source.relative_to(codex).as_posix()
        threads = backup.read_json(package / "manifest" / "threads.json")
        thread = next(item for item in threads if item.get("id") == THREAD_ID)
        package_manifest = backup.read_json(package / "manifest" / "package.json")
        backup_report = backup.read_json(package / "reports" / "backup-report.json")
        package_valid = validate(package, False).get("valid")
        preserved_payload = package / Path(*Path(preserved_relative).parts)
        preserved_exact = bool(
            preserved_payload.is_file()
            and preserved_payload.read_bytes() == duplicate_source.read_bytes()
        )
        if preserved_payload.is_file():
            preserved_payload.unlink()
        missing_preserved_rejected = not validate(package, False).get("valid")
        results.append(
            bool(
                package_valid
                and resolution.get("resolvedDuplicateThreadIds") == [THREAD_ID]
                and resolution.get("unresolvedDuplicateThreadIds") == []
                and resolved[0].get("contentRelation")
                == ("different" if divergent else "identical")
                and resolved[0].get("canonical", {}).get("sourcePath")
                == str(canonical_source)
                and canonical_relative
                == resolution.get("canonicalPathsByThreadId", {}).get(THREAD_ID)
                and thread.get("backupRelativePath") == canonical_relative
                and thread.get("rolloutCollection") == "sessions"
                and len(preserved) == 1
                and preserved_exact
                and missing_preserved_rejected
                and not (package / Path(*Path(duplicate_relative).parts)).exists()
                and package_manifest.get("counts", {}).get(
                    "resolvedDuplicateThreads"
                )
                == 1
                and package_manifest.get("counts", {}).get(
                    "nonCanonicalRolloutsPreserved"
                )
                == 1
                and backup_report.get("rolloutResolution", {}).get(
                    "resolvedDuplicateThreads"
                )
                == 1
                and source_before == _hash_tree(profile)
            )
        )
    return results[0], results[1]


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
    quarantine_failure_profile = root / "quarantine-failure-user"
    activation_failure_profile = root / "activation-failure-user"
    older_target_profile = root / "older-target-user"
    source_codex, source_project = _write_source(source_profile)
    _, target_project = _write_target(target_profile, "PRESERVE-A")
    _, rollback_project = _write_target(rollback_profile, "PRESERVE-B")
    _, quarantine_failure_project = _write_target(
        quarantine_failure_profile, "PRESERVE-QUARANTINE"
    )
    _, activation_failure_project = _write_target(
        activation_failure_profile, "PRESERVE-ACTIVATION"
    )
    _write_older_target(older_target_profile, "OLDER")
    source_before = _hash_tree(source_profile)
    rollout_preflight_diagnostics = _rollout_preflight_diagnostics_test(
        root, source_profile
    )
    path_budget_preflight = _path_budget_test(root)
    destination_prompt = _destination_prompt_test()
    reconstructable_cache_warning, mandatory_copy_failure = (
        _reconstructable_cache_policy_test(root, source_profile)
    )
    identical_rollout_resolved, different_rollout_resolved = (
        _rollout_resolution_test(root, source_profile)
    )
    selection_preview = backup.build_backup_preview(source_profile, source_codex)
    preview_source_unchanged = source_before == _hash_tree(source_profile)
    preview_project = selection_preview.get("projects", [{}])[0]
    backup_selection_preview_complete = bool(
        preview_source_unchanged
        and selection_preview.get("conversations") == 3
        and selection_preview.get("codex", {}).get("locked")
        and len(selection_preview.get("projects", [])) == 1
        and preview_project.get("path") == str(source_project.resolve(strict=False))
        and preview_project.get("fileCount") == 3
        and preview_project.get("totalBytes") == 70
        and bool(preview_project.get("pathBudgetItems"))
        and bool(selection_preview.get("codex", {}).get("pathBudgetItems"))
        and selection_preview.get("totals", {}).get("fileCount", 0) > 3
        and selection_preview.get("totals", {}).get("totalBytes", 0) > 70
        and selection_preview.get("portabilityAudit", {}).get("status") == "portable"
        and selection_preview.get("portabilityAudit", {}).get("privacy", {}).get(
            "containsPathValues"
        ) is False
    )
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
                "projectRegistryPath": str(
                    root / "source-lifeboat-state" / "project-registry.json"
                ),
                "lineageStatePath": str(
                    root / "source-lifeboat-state" / "lineage-state.json"
                ),
                "deviceStatePath": str(
                    root / "source-lifeboat-state" / "device.json"
                ),
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
    progress_events: list[tuple[int, int, str]] = []
    backup.set_status_callback(
        lambda current, total, message: progress_events.append(
            (current, total, message)
        )
    )
    try:
        package = backup.build_backup(args)
    finally:
        backup.set_status_callback(None)

    excluded_destination = root / "excluded-usb"
    excluded_config = root / "excluded-backup-config.json"
    excluded_config.write_text(
        json.dumps(
            {
                "configVersion": 1,
                "destinationRoot": str(excluded_destination),
                "includeAttachments": True,
                "projects": [],
                "excludedProjectPaths": [str(source_project)],
                "additionalPortablePaths": [],
                "excludeDirectoryNames": [],
                "projectRegistryPath": str(root / "excluded-state" / "project-registry.json"),
                "lineageStatePath": str(root / "excluded-state" / "lineage-state.json"),
                "deviceStatePath": str(root / "excluded-state" / "device.json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    excluded_package = backup.build_backup(
        argparse.Namespace(
            config=str(excluded_config),
            destination=str(excluded_destination),
            source_profile=str(source_profile),
            source_codex_home=str(source_codex),
            allow_running_test=True,
        )
    )
    excluded_snapshot = sqlite3.connect(
        excluded_package / "codex" / "state.snapshot.sqlite"
    )
    try:
        excluded_thread_project_ids = {
            row[0]
            for row in excluded_snapshot.execute('SELECT "project_id" FROM "threads"')
        }
        excluded_database_projects = int(
            excluded_snapshot.execute('SELECT count(*) FROM "projects"').fetchone()[0]
        )
        excluded_database_roots = int(
            excluded_snapshot.execute('SELECT count(*) FROM "project_roots"').fetchone()[0]
        )
    finally:
        excluded_snapshot.close()
    excluded_portable_state = backup.read_json(
        excluded_package / "codex" / "portable-global-state.json"
    )
    excluded_manifest = backup.read_json(
        excluded_package / "manifest" / "package.json"
    )
    excluded_report = backup.read_json(
        excluded_package / "reports" / "backup-report.json"
    )
    selective_project_exclusion_complete = bool(
        validate(excluded_package, False).get("valid")
        and backup.read_json(excluded_package / "manifest" / "projects.json") == []
        and not (excluded_package / "projects").exists()
        and excluded_manifest.get("counts", {}).get("threads") == 3
        and excluded_manifest.get("counts", {}).get("projects") == 0
        and excluded_manifest.get("selection", {}).get("excludedProjects") == 1
        and excluded_report.get("selection", {}).get("excludedProjectPaths")
        == [str(source_project)]
        and excluded_thread_project_ids == {None}
        and excluded_database_projects == 0
        and excluded_database_roots == 0
        and PROJECT_ID not in (excluded_portable_state.get("local-projects") or {})
        and THREAD_ID
        not in (excluded_portable_state.get("thread-project-assignments") or {})
        and THREAD_ID in (excluded_portable_state.get("projectless-thread-ids") or [])
    )
    source_after = _hash_tree(source_profile)
    package_validation = validate(package, False)
    from .gui import _backup_result_model

    visual_backup_summary = _backup_result_model(package, package_validation)
    # The path-budget evidence report is part of every package. A frozen portable
    # build also includes its own executable so the restore tool travels with it.
    expected_visual_file_count = 23 if getattr(sys, "frozen", False) else 22
    visual_backup_summary_complete = bool(
        visual_backup_summary.get("valid")
        and visual_backup_summary.get("metrics", {}).get("chats") == 3
        and visual_backup_summary.get("metrics", {}).get("projects") == 1
        and visual_backup_summary.get("metrics", {}).get("files")
        == expected_visual_file_count
        and visual_backup_summary.get("conversations", {}).get("archived") == 1
        and visual_backup_summary.get("conversations", {}).get("pinned") == 1
        and visual_backup_summary.get("attachments", {}).get("copied") == 1
        and visual_backup_summary.get("attachments", {}).get("missing") == 1
        and visual_backup_summary.get("warnings", {}).get("missingAttachments") == 1
        and visual_backup_summary.get("lineage") == "root"
    )
    plan_source_before = _hash_tree(source_profile)
    plan_package_before = _hash_tree(package)
    read_only_plan = restore_plan.build_restore_plan(
        package, source_profile, allow_running_test=True
    )
    plan_source_after = _hash_tree(source_profile)
    plan_package_after = _hash_tree(package)
    conflict_plan = restore_plan.build_restore_plan(
        package, target_profile, allow_running_test=True
    )
    plan_preview_complete = bool(
        read_only_plan.get("ready")
        and read_only_plan.get("writeSet")
        and read_only_plan.get("diskRequirements")
        and all(
            item.get("state") == "identical"
            for item in read_only_plan.get("items", [])
            if item.get("kind") in {"project", "conversation"}
        )
    )
    plan_conflicts_block = bool(
        not conflict_plan.get("ready")
        and conflict_plan.get("counts", {}).get("conflicting", 0) >= 1
        and conflict_plan.get("counts", {}).get("destination-only", 0) >= 1
        and conflict_plan.get("blockingReasons")
    )
    prefix_classifier_safe, prefix_classifier_strict = (
        _conversation_prefix_classifier_test(root)
    )
    prefix_profile = root / "prefix-sync-user"
    _copy_profile_fixture(source_profile, prefix_profile)
    prefix_connection = sqlite3.connect(prefix_profile / ".codex" / "state_5.sqlite")
    try:
        prefix_rollout_value = prefix_connection.execute(
            'SELECT "rollout_path" FROM "threads" WHERE "id"=?',
            (THREAD_ID,),
        ).fetchone()[0]
    finally:
        prefix_connection.close()
    prefix_rollout = Path(str(prefix_rollout_value).replace("\\\\?\\", ""))
    prefix_lines = prefix_rollout.read_text(encoding="utf-8-sig").splitlines()
    if len(prefix_lines) < 2:
        raise RuntimeError("Prefix synchronization fixture needs at least two records.")
    prefix_rollout.write_text("\n".join(prefix_lines[:-1]) + "\n", encoding="utf-8")
    prefix_source_before = _hash_tree(source_profile)
    prefix_package_before = _hash_tree(package)
    prefix_plan = restore_plan.build_restore_plan(
        package, prefix_profile, allow_running_test=True
    )
    prefix_item = next(
        item
        for item in prefix_plan.get("items", [])
        if item.get("key") == f"conversation/{THREAD_ID}"
    )
    prefix_plan_read_only = bool(
        prefix_source_before == _hash_tree(source_profile)
        and prefix_package_before == _hash_tree(package)
    )
    prefix_prepared = restore.prepare_restore(
        package,
        prefix_profile,
        allow_running_test=True,
        comparison_plan=prefix_plan,
    )
    restore.restore_backup(
        package,
        prefix_profile,
        Path(prefix_prepared["safetyRoot"]),
    )
    prefix_validation = restore.verify_restored(package, prefix_profile)
    prefix_repeat_plan = restore_plan.build_restore_plan(
        package, prefix_profile, allow_running_test=True
    )
    prefix_sync_automatic = bool(
        prefix_plan.get("ready")
        and prefix_item.get("state") == "incoming"
        and prefix_item.get("proposedAction") == "replace"
        and prefix_item.get("decision") == "automatic"
        and prefix_item.get("prefixSync", {}).get("automatic") is True
        and prefix_item.get("prefixSync", {}).get("additionalSourceRecords") == 1
        and prefix_plan_read_only
        and prefix_validation.get("valid")
        and all(
            item.get("state") == "identical"
            for item in prefix_repeat_plan.get("items", [])
            if item.get("kind") in {"project", "conversation"}
        )
    )
    planned_target_profile = root / "planned-target-user"
    shutil.copytree(source_profile, planned_target_profile)
    planned_project = planned_target_profile / "Documents" / "DemoProject"
    planned_project_before = _hash_tree(planned_project)
    executable_plan = restore_plan.build_restore_plan(
        package, planned_target_profile, allow_running_test=True
    )
    planned_prepared = restore.prepare_restore(
        package,
        planned_target_profile,
        allow_running_test=True,
        comparison_plan=executable_plan,
    )
    planned_restore = restore.restore_backup(
        package,
        planned_target_profile,
        Path(planned_prepared["safetyRoot"]),
    )
    planned_actions_match_execution = bool(
        executable_plan.get("ready")
        and planned_restore.get("projectFilesCopied") == 0
        and _hash_tree(planned_project) == planned_project_before
        and planned_restore.get("comparisonPlan", {}).get("planVersion")
        == restore_plan.PLAN_VERSION
        and restore.verify_restored(package, planned_target_profile).get("valid")
    )
    legacy_plan_package = root / "legacy-plan-package"
    shutil.copytree(package, legacy_plan_package)
    (legacy_plan_package / "manifest" / "lineage.json").unlink()
    legacy_mappings = backup.read_json(
        legacy_plan_package / "manifest" / "path-mappings.json"
    )
    legacy_mappings["mappingVersion"] = 1
    for item in legacy_mappings.get("projects", []):
        item.pop("location", None)
    backup.write_json(
        legacy_plan_package / "manifest" / "path-mappings.json", legacy_mappings
    )
    legacy_comparison_plan = restore_plan.build_restore_plan(
        legacy_plan_package, source_profile, allow_running_test=True
    )
    legacy_comparison_supported = bool(
        legacy_comparison_plan.get("ready")
        and legacy_comparison_plan.get("counts", {}).get("conflicting") == 0
    )

    conversation_profile = root / "conversation-decision-user"
    _copy_profile_fixture(source_profile, conversation_profile)
    _change_destination_conversation(conversation_profile, THREAD_ID)
    _add_destination_conversation(conversation_profile)
    conversation_plan = restore_plan.build_restore_plan(
        package, conversation_profile, allow_running_test=True
    )
    conflict_key = f"conversation/{THREAD_ID}"
    destination_only_key = f"conversation/{DESTINATION_ONLY_THREAD_ID}"
    decision_items = {
        str(item.get("key")): item
        for item in conversation_plan.get("items", [])
        if item.get("kind") == "conversation"
    }
    cancelled_plan = restore_plan.resolve_conversation_decision(
        conversation_plan, conflict_key, "cancel"
    )
    skipped_plan = restore_plan.resolve_conversation_decision(
        conversation_plan, destination_only_key, "skip"
    )
    skipped_plan = restore_plan.resolve_conversation_decision(
        skipped_plan, conflict_key, "keep-source"
    )
    conversation_plan = restore_plan.resolve_conversation_decision(
        conversation_plan, conflict_key, "keep-both"
    )
    conversation_plan = restore_plan.resolve_conversation_decision(
        conversation_plan, destination_only_key, "keep-target"
    )
    resolved_conflict_item = next(
        item
        for item in conversation_plan["items"]
        if item.get("key") == conflict_key
    )
    clone_id = str(resolved_conflict_item["cloneId"])
    conversation_choices_complete = bool(
        decision_items[conflict_key].get("state") == "conflicting"
        and decision_items[destination_only_key].get("state") == "destination-only"
        and set(decision_items[conflict_key].get("availableDecisions", []))
        == set(restore_plan.CONVERSATION_DECISIONS)
        and cancelled_plan.get("cancelled")
        and not cancelled_plan.get("ready")
        and skipped_plan.get("ready")
        and conversation_plan.get("ready")
        and not restore_plan.validate_plan_decisions(conversation_plan)
    )
    conversation_prepared = restore.prepare_restore(
        package,
        conversation_profile,
        allow_running_test=True,
        comparison_plan=conversation_plan,
    )
    conversation_restored = restore.restore_backup(
        package,
        conversation_profile,
        Path(conversation_prepared["safetyRoot"]),
    )
    conversation_validation = restore.verify_restored(
        package,
        conversation_profile,
        comparison_plan=conversation_plan,
    )
    conversation_connection = sqlite3.connect(
        conversation_profile / ".codex" / "state_5.sqlite"
    )
    try:
        conversation_rows = {
            str(row[0]): row
            for row in conversation_connection.execute(
                "SELECT id,title,archived,is_pinned,project_id,rollout_path FROM threads"
            ).fetchall()
        }
        cloned_tools = int(
            conversation_connection.execute(
                "SELECT count(*) FROM thread_dynamic_tools WHERE thread_id=?",
                (clone_id,),
            ).fetchone()[0]
        )
        cloned_edges = int(
            conversation_connection.execute(
                "SELECT count(*) FROM thread_spawn_edges WHERE parent_thread_id=? OR child_thread_id=?",
                (clone_id, clone_id),
            ).fetchone()[0]
        )
        retained_destination_project = int(
            conversation_connection.execute(
                "SELECT count(*) FROM projects WHERE id=?",
                (DESTINATION_ONLY_PROJECT_ID,),
            ).fetchone()[0]
        )
        retained_destination_root = conversation_connection.execute(
            "SELECT path FROM project_roots WHERE project_id=?",
            (DESTINATION_ONLY_PROJECT_ID,),
        ).fetchone()
    finally:
        conversation_connection.close()
    clone_rollout = Path(str(conversation_rows[clone_id][5]))
    source_rollout_after = Path(str(conversation_rows[THREAD_ID][5]))
    destination_rollout_after = Path(
        str(conversation_rows[DESTINATION_ONLY_THREAD_ID][5])
    )
    clone_rollout_id, clone_rollout_error = backup.parse_session_meta(clone_rollout)
    conversation_index = backup.read_session_index(
        conversation_profile / ".codex" / "session_index.jsonl"
    )
    expected_conversation_ids = {
        THREAD_ID,
        PROJECTLESS_THREAD_ID,
        ARCHIVED_THREAD_ID,
        DESTINATION_ONLY_THREAD_ID,
        clone_id,
    }
    conversation_mirror_exact = bool(
        conversation_validation.get("valid")
        and set(conversation_rows) == expected_conversation_ids
        and len(conversation_rows) == len(expected_conversation_ids)
        and conversation_rows[DESTINATION_ONLY_THREAD_ID][2] == 1
        and conversation_rows[DESTINATION_ONLY_THREAD_ID][3] == 1
        and conversation_rows[DESTINATION_ONLY_THREAD_ID][4]
        == DESTINATION_ONLY_PROJECT_ID
        and conversation_rows[clone_id][3] == 1
        and str(conversation_rows[clone_id][1]).endswith("(destination copy)")
        and clone_rollout_id == clone_id
        and not clone_rollout_error
        and "independent destination edit" in clone_rollout.read_text(encoding="utf-8")
        and "independent destination edit" not in source_rollout_after.read_text(encoding="utf-8")
        and destination_rollout_after.is_file()
        and cloned_tools == 1
        and cloned_edges == 1
        and retained_destination_project == 1
        and retained_destination_root
        and Path(str(retained_destination_root[0])).is_dir()
        and conversation_restored.get("databaseCounts", {}).get(
            "retainedTargetProjectsForThreads"
        ) == 1
        and set(conversation_index.get("threadIds", []))
        == {THREAD_ID, PROJECTLESS_THREAD_ID, clone_id}
        and not conversation_index.get("duplicateThreadIds")
        and conversation_restored.get("targetConversationsRetained") == 1
        and conversation_restored.get("targetConversationsCloned") == 1
        and conversation_restored.get("recentIndexEntries") == 3
    )
    repeated_conversation_before = _conversation_snapshot(conversation_profile)
    repeated_conversation_plan = restore_plan.build_restore_plan(
        package, conversation_profile, allow_running_test=True
    )
    for item in list(repeated_conversation_plan.get("items", [])):
        if item.get("kind") == "conversation" and item.get("blocking"):
            repeated_conversation_plan = restore_plan.resolve_conversation_decision(
                repeated_conversation_plan, str(item["key"]), "keep-target"
            )
    repeated_conversation_prepared = restore.prepare_restore(
        package,
        conversation_profile,
        allow_running_test=True,
        comparison_plan=repeated_conversation_plan,
    )
    restore.restore_backup(
        package,
        conversation_profile,
        Path(repeated_conversation_prepared["safetyRoot"]),
    )
    repeated_conversation_idempotent = bool(
        repeated_conversation_plan.get("ready")
        and _conversation_snapshot(conversation_profile)
        == repeated_conversation_before
    )

    delete_conversation_profile = root / "conversation-delete-user"
    _copy_profile_fixture(source_profile, delete_conversation_profile)
    _add_destination_conversation(delete_conversation_profile)
    delete_conversation_plan = restore_plan.build_restore_plan(
        package, delete_conversation_profile, allow_running_test=True
    )
    delete_conversation_plan = restore_plan.resolve_conversation_decision(
        delete_conversation_plan, destination_only_key, "keep-source"
    )
    delete_conversation_prepared = restore.prepare_restore(
        package,
        delete_conversation_profile,
        allow_running_test=True,
        comparison_plan=delete_conversation_plan,
    )
    restore.restore_backup(
        package,
        delete_conversation_profile,
        Path(delete_conversation_prepared["safetyRoot"]),
    )
    deleted_snapshot = _conversation_snapshot(delete_conversation_profile)
    explicit_conversation_delete = bool(
        delete_conversation_plan.get("ready")
        and set(deleted_snapshot["rollouts"])
        == {THREAD_ID, PROJECTLESS_THREAD_ID, ARCHIVED_THREAD_ID}
        and DESTINATION_ONLY_THREAD_ID not in deleted_snapshot["rollouts"]
    )

    conversation_rollback_profile = root / "conversation-rollback-user"
    _copy_profile_fixture(source_profile, conversation_rollback_profile)
    _change_destination_conversation(conversation_rollback_profile, THREAD_ID)
    _add_destination_conversation(conversation_rollback_profile)
    conversation_rollback_before = _conversation_snapshot(
        conversation_rollback_profile
    )
    conversation_rollback_plan = restore_plan.build_restore_plan(
        package, conversation_rollback_profile, allow_running_test=True
    )
    conversation_rollback_plan = restore_plan.resolve_conversation_decision(
        conversation_rollback_plan, conflict_key, "keep-both"
    )
    conversation_rollback_plan = restore_plan.resolve_conversation_decision(
        conversation_rollback_plan, destination_only_key, "keep-target"
    )
    conversation_rollback_prepared = restore.prepare_restore(
        package,
        conversation_rollback_profile,
        allow_running_test=True,
        comparison_plan=conversation_rollback_plan,
    )
    conversation_rollback_triggered = False
    try:
        restore.restore_backup(
            package,
            conversation_rollback_profile,
            Path(conversation_rollback_prepared["safetyRoot"]),
            fail_after_conversations_for_test=True,
        )
    except Exception:
        conversation_rollback_triggered = True
    conversation_rollback_journal = backup.read_json(
        Path(conversation_rollback_prepared["safetyRoot"])
        / "restore-journal.json"
    )
    conversation_rollback_preserved = bool(
        conversation_rollback_triggered
        and conversation_rollback_journal.get("status") == "rolled-back"
        and _conversation_snapshot(conversation_rollback_profile)
        == conversation_rollback_before
    )

    retained_project_profile = root / "project-retain-user"
    _copy_profile_fixture(source_profile, retained_project_profile)
    retained_fixture = _add_registered_destination_project(
        retained_project_profile, "RETAIN"
    )
    retained_project_plan = restore_plan.build_restore_plan(
        package, retained_project_profile, allow_running_test=True
    )
    retained_project_key = f"project/{retained_fixture['rootId']}"
    retained_project_item = next(
        item
        for item in retained_project_plan.get("items", [])
        if item.get("key") == retained_project_key
    )
    retained_project_prepared = restore.prepare_restore(
        package,
        retained_project_profile,
        allow_running_test=True,
        comparison_plan=retained_project_plan,
    )
    retained_project_result = restore.restore_backup(
        package,
        retained_project_profile,
        Path(retained_project_prepared["safetyRoot"]),
    )
    retained_project_registry = project_identity.load_registry(
        Path(retained_fixture["registryPath"])
    )
    retained_registration = _project_registration_state(
        retained_project_profile, str(retained_fixture["codexProjectId"])
    )
    destination_project_retained_by_default = bool(
        retained_project_plan.get("ready")
        and retained_project_item.get("decision") == "retain-default"
        and retained_project_item.get("proposedAction") == "retain"
        and set(retained_project_item.get("availableDecisions", []))
        == set(restore_plan.PROJECT_DECISIONS_DESTINATION_ONLY)
        and _hash_tree(Path(retained_fixture["path"])) == retained_fixture["hashes"]
        and all(retained_registration.values())
        and any(
            root_item.get("rootId") == retained_fixture["rootId"]
            for project_item in retained_project_registry.get("projects", [])
            for root_item in project_item.get("roots", [])
        )
        and retained_project_result.get("destinationProjectsArchived") == 0
        and retained_project_result.get("destinationProjectsRemovedToRecovery") == 0
        and restore.verify_restored(package, retained_project_profile).get("valid")
    )

    archived_project_profile = root / "project-archive-user"
    _copy_profile_fixture(source_profile, archived_project_profile)
    archived_fixture = _add_registered_destination_project(
        archived_project_profile,
        "ARCHIVE",
        root / "external-project-archive",
    )
    archived_project_plan = restore_plan.build_restore_plan(
        package, archived_project_profile, allow_running_test=True
    )
    archived_project_plan = restore_plan.resolve_project_decision(
        archived_project_plan,
        f"project/{archived_fixture['rootId']}",
        "archive",
    )
    archived_project_prepared = restore.prepare_restore(
        package,
        archived_project_profile,
        allow_running_test=True,
        comparison_plan=archived_project_plan,
    )
    archived_project_result = restore.restore_backup(
        package,
        archived_project_profile,
        Path(archived_project_prepared["safetyRoot"]),
    )
    archived_disposition = Path(
        str(archived_project_result["destinationProjectDispositionPaths"][0])
    )
    archived_registration = _project_registration_state(
        archived_project_profile, str(archived_fixture["codexProjectId"])
    )
    archived_registry = project_identity.load_registry(
        Path(archived_fixture["registryPath"])
    )
    destination_project_archive_complete = bool(
        archived_project_plan.get("ready")
        and not Path(archived_fixture["path"]).exists()
        and archived_disposition.parent.name == "Codex Lifeboat Project Archives"
        and _hash_tree(archived_disposition) == archived_fixture["hashes"]
        and not any(archived_registration.values())
        and not any(
            root_item.get("rootId") == archived_fixture["rootId"]
            for project_item in archived_registry.get("projects", [])
            for root_item in project_item.get("roots", [])
        )
        and archived_project_result.get("destinationProjectsArchived") == 1
        and restore.verify_restored(package, archived_project_profile).get("valid")
    )

    deleted_project_profile = root / "project-delete-user"
    _copy_profile_fixture(source_profile, deleted_project_profile)
    deleted_fixture = _add_registered_destination_project(
        deleted_project_profile, "DELETE"
    )
    deleted_project_plan = restore_plan.build_restore_plan(
        package, deleted_project_profile, allow_running_test=True
    )
    delete_cancelled_plan = restore_plan.resolve_project_decision(
        deleted_project_plan,
        f"project/{deleted_fixture['rootId']}",
        "cancel",
    )
    deleted_project_plan = restore_plan.resolve_project_decision(
        deleted_project_plan,
        f"project/{deleted_fixture['rootId']}",
        "delete",
    )
    deleted_project_prepared = restore.prepare_restore(
        package,
        deleted_project_profile,
        allow_running_test=True,
        comparison_plan=deleted_project_plan,
    )
    deleted_project_result = restore.restore_backup(
        package,
        deleted_project_profile,
        Path(deleted_project_prepared["safetyRoot"]),
    )
    deleted_disposition = Path(
        str(deleted_project_result["destinationProjectDispositionPaths"][0])
    )
    deleted_registration = _project_registration_state(
        deleted_project_profile, str(deleted_fixture["codexProjectId"])
    )
    destination_project_delete_recoverable = bool(
        delete_cancelled_plan.get("cancelled")
        and not delete_cancelled_plan.get("ready")
        and deleted_project_plan.get("ready")
        and not Path(deleted_fixture["path"]).exists()
        and ".codex-lifeboat-recovery" in deleted_disposition.parts
        and _hash_tree(deleted_disposition) == deleted_fixture["hashes"]
        and not any(deleted_registration.values())
        and deleted_project_result.get("destinationProjectsRemovedToRecovery") == 1
        and restore.verify_restored(package, deleted_project_profile).get("valid")
    )

    project_conflict_profile = root / "project-conflict-user"
    _copy_profile_fixture(source_profile, project_conflict_profile)
    project_conflict_target = (
        project_conflict_profile / "Documents" / "DemoProject"
    )
    (project_conflict_target / "LOCAL-CHANGE.txt").write_text(
        "keep this archived\n", encoding="utf-8"
    )
    conflict_target_before = _hash_tree(project_conflict_target)
    project_conflict_plan = restore_plan.build_restore_plan(
        package, project_conflict_profile, allow_running_test=True
    )
    project_conflict_item = next(
        item
        for item in project_conflict_plan.get("items", [])
        if item.get("kind") == "project" and item.get("source") is not None
    )
    project_keep_target_plan = restore_plan.resolve_project_decision(
        project_conflict_plan, str(project_conflict_item["key"]), "keep-target"
    )
    project_keep_target_profile = root / "project-keep-target-user"
    _copy_profile_fixture(source_profile, project_keep_target_profile)
    project_keep_target_path = (
        project_keep_target_profile / "Documents" / "DemoProject"
    )
    (project_keep_target_path / "LOCAL-CHANGE.txt").write_text(
        "keep computer\n", encoding="utf-8"
    )
    project_keep_target_before = _hash_tree(project_keep_target_path)
    project_keep_target_execution_plan = restore_plan.build_restore_plan(
        package, project_keep_target_profile, allow_running_test=True
    )
    project_keep_target_item = next(
        item
        for item in project_keep_target_execution_plan.get("items", [])
        if item.get("kind") == "project" and item.get("source") is not None
    )
    project_keep_target_execution_plan = restore_plan.resolve_project_decision(
        project_keep_target_execution_plan,
        str(project_keep_target_item["key"]),
        "keep-target",
    )
    project_keep_target_prepared = restore.prepare_restore(
        package,
        project_keep_target_profile,
        allow_running_test=True,
        comparison_plan=project_keep_target_execution_plan,
    )
    project_keep_target_result = restore.restore_backup(
        package,
        project_keep_target_profile,
        Path(project_keep_target_prepared["safetyRoot"]),
    )
    project_keep_target_preserved = bool(
        project_keep_target_execution_plan.get("ready")
        and _hash_tree(project_keep_target_path) == project_keep_target_before
        and project_keep_target_result.get("projectFilesCopied") == 0
        and restore.verify_restored(package, project_keep_target_profile).get("valid")
    )
    project_conflict_plan = restore_plan.resolve_project_decision(
        project_conflict_plan, str(project_conflict_item["key"]), "archive"
    )
    project_conflict_prepared = restore.prepare_restore(
        package,
        project_conflict_profile,
        allow_running_test=True,
        comparison_plan=project_conflict_plan,
    )
    project_conflict_result = restore.restore_backup(
        package,
        project_conflict_profile,
        Path(project_conflict_prepared["safetyRoot"]),
    )
    conflict_transaction = next(
        item
        for item in project_conflict_result.get("projects", [])
        if item.get("strategy") == "transactional-mirror"
    )
    project_conflict_archive = Path(str(conflict_transaction["quarantinePath"]))
    project_conflict_choices_complete = bool(
        set(project_conflict_item.get("availableDecisions", []))
        == set(restore_plan.PROJECT_DECISIONS_CONFLICT)
        and project_keep_target_plan.get("ready")
        and project_keep_target_preserved
        and project_conflict_plan.get("ready")
        and project_conflict_plan.get("items")
        and conflict_transaction.get("previousTargetDisposition") == "archive"
        and _hash_tree(project_conflict_archive) == conflict_target_before
        and not (project_conflict_target / "LOCAL-CHANGE.txt").exists()
        and (project_conflict_target / "README.md").read_text(encoding="utf-8")
        == "# New project\n"
        and restore.verify_restored(package, project_conflict_profile).get("valid")
    )

    project_rollback_profile = root / "project-disposition-rollback-user"
    _copy_profile_fixture(source_profile, project_rollback_profile)
    rollback_destination_fixture = _add_registered_destination_project(
        project_rollback_profile, "ROLLBACK"
    )
    rollback_destination_plan = restore_plan.build_restore_plan(
        package, project_rollback_profile, allow_running_test=True
    )
    rollback_destination_plan = restore_plan.resolve_project_decision(
        rollback_destination_plan,
        f"project/{rollback_destination_fixture['rootId']}",
        "archive",
    )
    rollback_destination_prepared = restore.prepare_restore(
        package,
        project_rollback_profile,
        allow_running_test=True,
        comparison_plan=rollback_destination_plan,
    )
    destination_project_rollback_triggered = False
    try:
        restore.restore_backup(
            package,
            project_rollback_profile,
            Path(rollback_destination_prepared["safetyRoot"]),
            fail_after_destination_project_move_for_test=True,
        )
    except Exception:
        destination_project_rollback_triggered = True
    rollback_destination_journal = backup.read_json(
        Path(rollback_destination_prepared["safetyRoot"]) / "restore-journal.json"
    )
    destination_project_rollback_preserved = bool(
        destination_project_rollback_triggered
        and rollback_destination_journal.get("status") == "rolled-back"
        and _hash_tree(Path(rollback_destination_fixture["path"]))
        == rollback_destination_fixture["hashes"]
        and all(
            _project_registration_state(
                project_rollback_profile,
                str(rollback_destination_fixture["codexProjectId"]),
            ).values()
        )
        and not any(
            Path(str(item.get("dispositionPath"))).exists()
            for item in rollback_destination_journal.get("projects", [])
            if item.get("strategy") == "destination-project-disposition"
        )
    )

    recovery_profile = root / "recovery-retention-user"
    recovery_profile.mkdir()
    recovery_source_database = source_profile / ".codex" / "state_5.sqlite"
    recovery_fixtures = [
        _write_recovery_fixture(
            recovery_profile,
            recovery_source_database,
            f"point-{sequence}",
            sequence,
            include_staging=sequence == 4,
            include_visible_archive=sequence == 1,
        )
        for sequence in range(1, 5)
    ]
    invalid_recovery_fixture = _write_recovery_fixture(
        recovery_profile,
        recovery_source_database,
        "point-invalid",
        5,
        status="restoring",
    )
    usb_recovery_sentinel = recovery_profile / "usb" / "Codex-PortableBackup-KEEP"
    usb_recovery_sentinel.mkdir(parents=True)
    (usb_recovery_sentinel / "DO-NOT-DELETE.txt").write_text(
        "usb backup", encoding="utf-8"
    )
    recovery_before = recovery.list_points(recovery_profile)
    recovery_cleanup = recovery.enforce_retention(recovery_profile)
    recovery_after = recovery.list_points(recovery_profile)
    recovery_second_cleanup = recovery.enforce_retention(recovery_profile)
    recovery_retention_complete = bool(
        recovery_before.get("validPoints") == 4
        and recovery_before.get("invalidPoints") == 1
        and recovery_cleanup.get("validPointsAfter") == 2
        and recovery_cleanup.get("invalidPointsRetained") == 1
        and len(recovery_cleanup.get("removedPoints", [])) == 2
        and recovery_cleanup.get("removedProjectPayloads") == 2
        and recovery_cleanup.get("stagingDirectoriesRemoved") == 1
        and recovery_after.get("validPoints") == 2
        and recovery_after.get("invalidPoints") == 1
        and recovery_fixtures[2]["point"].is_dir()
        and recovery_fixtures[3]["point"].is_dir()
        and not recovery_fixtures[0]["point"].exists()
        and not recovery_fixtures[1]["point"].exists()
        and not recovery_fixtures[0]["payload"].exists()
        and not recovery_fixtures[1]["payload"].exists()
        and not recovery_fixtures[0]["payload"].parent.exists()
        and not recovery_fixtures[1]["payload"].parent.exists()
        and not recovery_fixtures[3]["staging"].exists()
        and recovery_fixtures[0]["visibleArchive"].is_dir()
        and invalid_recovery_fixture["point"].is_dir()
        and usb_recovery_sentinel.is_dir()
        and not recovery_second_cleanup.get("removedPoints")
        and recovery_second_cleanup.get("validPointsAfter") == 2
        and windows.recovery_points_folder(recovery_profile)
        != recovery_profile / ".codex"
    )
    package_manifest = backup.read_json(package / "manifest" / "package.json")
    path_mappings = backup.read_json(package / "manifest" / "path-mappings.json")
    inventory = backup.read_json(package / "manifest" / "inventory.json")
    first_lineage = backup.read_json(package / "manifest" / "lineage.json")
    portable_locations_recorded = bool(
        package_manifest.get("formatVersion") == "2.4"
        and path_mappings.get("mappingVersion") == 2
        and path_mappings.get("projects")
        and all(
            not path_model.validate_location(item.get("location"))
            for item in path_mappings.get("projects", [])
        )
    )
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
    managed_recovery_location = bool(
        Path(prepared["safetyRoot"]).parent.resolve(strict=False)
        == windows.recovery_points_folder(target_profile).resolve(strict=False)
        and restored.get("recoveryRetention", {}).get("validPointsAfter") == 1
    )
    restored_validation = restore.verify_restored(package, target_profile)
    identity_manifest = backup.read_json(
        package / "manifest" / "project-identities.json"
    )
    target_identity_registry = project_identity.load_registry(
        windows.project_registry_path(target_profile)
    )
    identities_installed = bool(
        identity_manifest.get("roots")
        and restored.get("projectIdentitiesRegistered")
        == len(identity_manifest["roots"])
        and not project_identity.validate_registry(target_identity_registry)
    )
    transaction_record = next(
        (
            item
            for item in restored.get("projects", [])
            if item.get("strategy") == "transactional-mirror"
        ),
        None,
    )
    transaction_quarantine = (
        Path(str(transaction_record["quarantinePath"]))
        if transaction_record
        else Path()
    )
    transactional_mirror_complete = bool(
        transaction_record
        and transaction_record.get("status") == "complete"
        and transaction_record.get("stagedVerification", {}).get("files") == 3
        and not Path(str(transaction_record["stagingPath"])).exists()
        and transaction_quarantine.is_dir()
        and (transaction_quarantine / "OLD.txt").read_text(encoding="utf-8")
        == "PRESERVE-A"
        and not (target_project / "OLD.txt").exists()
        and len(list(target_project.parent.glob("DemoProject*"))) == 1
    )
    idempotent_project_before = _hash_tree(target_project)
    idempotent_plan = restore_plan.build_restore_plan(
        package, target_profile, allow_running_test=True
    )
    idempotent_prepared = restore.prepare_restore(
        package,
        target_profile,
        allow_running_test=True,
        comparison_plan=idempotent_plan,
    )
    idempotent_restore = restore.restore_backup(
        package, target_profile, Path(idempotent_prepared["safetyRoot"])
    )
    repeated_restore_idempotent = bool(
        idempotent_plan.get("ready")
        and all(
            item.get("proposedAction") == "none"
            for item in idempotent_plan.get("items", [])
            if item.get("kind") == "project"
            and item.get("source") is not None
        )
        and idempotent_restore.get("projectFilesCopied") == 0
        and not idempotent_restore.get("projects")
        and _hash_tree(target_project) == idempotent_project_before
        and not list(target_project.parent.glob(".codex-lifeboat-stage-*"))
    )

    return_destination = root / "return-usb"
    return_config = root / "return-backup-config.json"
    return_config.write_text(
        json.dumps(
            {
                "configVersion": 1,
                "destinationRoot": str(return_destination),
                "includeAttachments": True,
                "projects": [],
                "additionalPortablePaths": [],
                "excludeDirectoryNames": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return_package = backup.build_backup(
        argparse.Namespace(
            config=str(return_config),
            destination=str(return_destination),
            source_profile=str(target_profile),
            source_codex_home=str(target_profile / ".codex"),
            allow_running_test=True,
        )
    )
    return_identity_manifest = backup.read_json(
        return_package / "manifest" / "project-identities.json"
    )
    return_lineage = backup.read_json(return_package / "manifest" / "lineage.json")
    first_identity_pairs = {
        (item["projectId"], item["rootId"])
        for item in identity_manifest.get("roots", [])
    }
    return_identity_pairs = {
        (item["projectId"], item["rootId"])
        for item in return_identity_manifest.get("roots", [])
    }
    identities_survive_round_trip = bool(
        first_identity_pairs and first_identity_pairs == return_identity_pairs
    )
    lineage_survives_round_trip = bool(
        first_lineage.get("relation") == "root"
        and first_lineage.get("parentBackupId") is None
        and return_lineage.get("relation") == "linear"
        and return_lineage.get("parentBackupId") == first_lineage.get("backupId")
        and return_lineage.get("sourceDeviceId")
        != first_lineage.get("sourceDeviceId")
        and return_lineage.get("counts", {}).get("changed") == 0
        and return_lineage.get("counts", {}).get("independentlyChanged") == 0
        and return_lineage.get("counts", {}).get("new") == 0
        and return_lineage.get("counts", {}).get("removed") == 0
        and return_lineage.get("counts", {}).get("unchanged")
        == len(return_lineage.get("items", []))
        and not lineage.validate_manifest(first_lineage)
        and not lineage.validate_manifest(return_lineage)
    )
    conversation_items = inventory.get("conversations", {}).get("items", [])
    conversation_by_id = {item.get("id"): item for item in conversation_items}
    inventory_complete = bool(
        set(conversation_by_id)
        == {THREAD_ID, PROJECTLESS_THREAD_ID, ARCHIVED_THREAD_ID}
        and inventory.get("conversations", {}).get("counts")
        == {
            "total": 3,
            "recent": 2,
            "archived": 1,
            "pinned": 1,
            "projectless": 2,
            "projectLinked": 1,
        }
        and conversation_by_id[PROJECTLESS_THREAD_ID].get("pinned") is True
        and conversation_by_id[PROJECTLESS_THREAD_ID].get("projectless") is True
        and conversation_by_id[ARCHIVED_THREAD_ID].get("state") == "archived"
        and conversation_by_id[ARCHIVED_THREAD_ID].get("indexPresent") is False
        and len(inventory.get("relationships", {}).get("spawnEdges", [])) == 1
        and len(inventory.get("relationships", {}).get("assignments", {})) == 1
        and len(
            inventory.get("relationships", {}).get("projectlessThreadIds", [])
        )
        == 2
        and len(inventory.get("relationships", {}).get("dynamicTools", [])) == 1
        and len(inventory.get("relationships", {}).get("sections", [])) == 1
        and inventory.get("sessions", {}).get("count") == 3
        and inventory.get("attachments", {}).get("copied") == 1
        and inventory.get("attachments", {}).get("missing") == 1
        and inventory.get("projects", {}).get("candidateCount") == 1
    )
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
        and (target_profile / ".codex" / "dictation-history").is_dir()
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

    missing_empty_tree = root / "missing-empty-tree-package"
    shutil.copytree(package, missing_empty_tree)
    shutil.rmtree(
        missing_empty_tree / "codex" / "portable-profile" / "dictation-history"
    )
    missing_empty_tree_rejected = not validate(missing_empty_tree, False)["valid"]

    quarantine_project_before = _hash_tree(quarantine_failure_project)
    quarantine_failure_prepared = restore.prepare_restore(
        package, quarantine_failure_profile, allow_running_test=True
    )
    quarantine_failure_triggered = False
    try:
        restore.restore_backup(
            package,
            quarantine_failure_profile,
            Path(quarantine_failure_prepared["safetyRoot"]),
            fail_after_project_quarantine_for_test=True,
        )
    except Exception:
        quarantine_failure_triggered = True
    quarantine_failure_journal = backup.read_json(
        Path(quarantine_failure_prepared["safetyRoot"]) / "restore-journal.json"
    )
    quarantine_failure_record = quarantine_failure_journal.get("projects", [{}])[0]
    quarantine_failure_rollback = bool(
        quarantine_failure_triggered
        and quarantine_failure_journal.get("status") == "rolled-back"
        and quarantine_failure_record.get("status") == "rolled-back"
        and _hash_tree(quarantine_failure_project) == quarantine_project_before
        and (quarantine_failure_project / "OLD.txt").read_text(encoding="utf-8")
        == "PRESERVE-QUARANTINE"
        and not Path(str(quarantine_failure_record.get("stagingPath"))).exists()
        and not Path(str(quarantine_failure_record.get("quarantinePath"))).exists()
        and not list(
            quarantine_failure_project.parent.glob(".codex-lifeboat-stage-*")
        )
    )

    activation_project_before = _hash_tree(activation_failure_project)
    activation_failure_prepared = restore.prepare_restore(
        package, activation_failure_profile, allow_running_test=True
    )
    activation_failure_triggered = False
    try:
        restore.restore_backup(
            package,
            activation_failure_profile,
            Path(activation_failure_prepared["safetyRoot"]),
            fail_after_project_activation_for_test=True,
        )
    except Exception:
        activation_failure_triggered = True
    activation_failure_journal = backup.read_json(
        Path(activation_failure_prepared["safetyRoot"]) / "restore-journal.json"
    )
    activation_failure_record = activation_failure_journal.get("projects", [{}])[0]
    activation_failure_rollback = bool(
        activation_failure_triggered
        and activation_failure_journal.get("status") == "rolled-back"
        and activation_failure_record.get("status") == "rolled-back"
        and _hash_tree(activation_failure_project) == activation_project_before
        and (activation_failure_project / "OLD.txt").read_text(encoding="utf-8")
        == "PRESERVE-ACTIVATION"
        and not Path(str(activation_failure_record.get("stagingPath"))).exists()
        and not Path(str(activation_failure_record.get("quarantinePath"))).exists()
        and not list(
            activation_failure_project.parent.glob(".codex-lifeboat-stage-*")
        )
    )

    rollback_auth_before = backup.sha256_file(rollback_profile / ".codex" / "auth.json")
    rollback_registry_path = windows.project_registry_path(rollback_profile)
    rollback_registry = project_identity.empty_registry()
    project_identity.assign_identity(
        rollback_registry, rollback_project, "Original rollback project", []
    )
    project_identity.save_registry(rollback_registry_path, rollback_registry)
    rollback_registry_hash_before = backup.sha256_file(rollback_registry_path)
    rollback_lineage_path = windows.lineage_state_path(rollback_profile)
    rollback_lineage_state = lineage.empty_state()
    rollback_lineage_state["baseBackupId"] = str(uuid.uuid4())
    rollback_lineage_state["items"] = {"test/original": "d" * 64}
    lineage.save_state(rollback_lineage_path, rollback_lineage_state)
    rollback_lineage_hash_before = backup.sha256_file(rollback_lineage_path)
    rollback_prepared = restore.prepare_restore(
        package, rollback_profile, allow_running_test=True
    )
    rollback_triggered = False
    try:
        restore.restore_backup(
            package,
            rollback_profile,
            Path(rollback_prepared["safetyRoot"]),
            fail_after_identity_for_test=True,
        )
    except Exception:
        rollback_triggered = True
    lineage_rollback_preserved = (
        backup.sha256_file(rollback_lineage_path) == rollback_lineage_hash_before
    )
    rollback_preserved = (
        rollback_triggered
        and (rollback_project / "OLD.txt").read_text(encoding="utf-8") == "PRESERVE-B"
        and backup.sha256_file(rollback_profile / ".codex" / "auth.json")
        == rollback_auth_before
        and backup.sha256_file(rollback_registry_path) == rollback_registry_hash_before
        and lineage_rollback_preserved
        and backup.read_json(Path(rollback_prepared["safetyRoot"]) / "restore-journal.json")[
            "status"
        ]
        == "rolled-back"
    )
    hashing_progress_complete = any(
        current == total and message.startswith("Hashing backup:")
        for current, total, message in progress_events
    )
    validation_progress_complete = any(
        total == 0 and "database, manifests and package structure" in message.lower()
        for _current, total, message in progress_events
    )
    progress_transitions_clear = bool(
        any(total == 0 for _current, total, _message in progress_events)
        and any(
            total == 0 and "database, manifests and package structure" in message.lower()
            for _current, total, message in progress_events
        )
        and progress_events[-1] == (1, 1, "Backup complete")
    )
    original_run_hidden = windows.run_hidden
    original_path_is_file = Path.is_file
    try:
        windows.run_hidden = lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Version: Unknown\n", stderr=""
        )
        unknown_version = windows.latest_version_check(
            {"detected": True, "version": "26.818.5229.0"}
        )
        Path.is_file = lambda _path: (_ for _ in ()).throw(
            OSError(1920, "WindowsApps alias unavailable")
        )
        inaccessible_winget = windows.latest_version_check(
            {"detected": True, "version": "26.818.5229.0"}
        )
    finally:
        Path.is_file = original_path_is_file
        windows.run_hidden = original_run_hidden
    unknown_version_does_not_warn = (
        unknown_version.get("checked") is False
        and unknown_version.get("isLatest") is None
        and inaccessible_winget.get("checked") is False
        and inaccessible_winget.get("isLatest") is None
    )
    usb_classification = (
        windows._include_as_usb_destination(windows.DRIVE_REMOVABLE, False)
        and windows._include_as_usb_destination(windows.DRIVE_FIXED, True)
        and not windows._include_as_usb_destination(windows.DRIVE_FIXED, False)
    )
    compressed_launch_detection = (
        windows.launched_from_compressed_folder(
            Path(tempfile.gettempdir()) / "portable.zip.123" / "Codex-Lifeboat.exe"
        )
        and not windows.launched_from_compressed_folder(
            root / "extracted" / "Codex-Lifeboat.exe"
        )
    )
    diagnostic_source_before = _hash_tree(source_profile)
    diagnostic_report = diagnostics.build_report(
        source_profile,
        source_profile / ".codex",
        process_probe=lambda: [],
        installation_probe=lambda: {
            "detected": True,
            "version": "26.818.5229.0",
        },
        drives_probe=lambda: [],
    )
    diagnostic_source_after = _hash_tree(source_profile)
    diagnostic_text = diagnostics.report_json(diagnostic_report)
    diagnostic_report_path = root / "diagnostic-report.json"
    diagnostics.save_report(diagnostic_report_path, diagnostic_report)
    diagnostic_report_saved = (
        backup.read_json(diagnostic_report_path)
        == json.loads(diagnostics.report_json(diagnostic_report))
        and not list(root.glob(".diagnostic-report.json.*.tmp"))
        and "_localPortabilityAudit" not in backup.read_json(diagnostic_report_path)
    )
    diagnostic_check_ids = {
        str(item.get("id")) for item in diagnostic_report.get("checks", [])
    }
    diagnostic_center_complete = bool(
        diagnostic_source_before == diagnostic_source_after
        and diagnostic_report_saved
        and diagnostic_report.get("privacy", {}).get("anonymized") is True
        and diagnostic_report.get("privacy", {}).get("containsAbsolutePaths") is False
        and str(source_profile).lower() not in diagnostic_text.lower()
        and source_profile.name.lower() not in diagnostic_text.lower()
        and diagnostic_report.get("inventory", {}).get("conversationCount") == 3
        and diagnostic_report.get("inventory", {}).get("projectCount") == 1
        and {
            "windows",
            "launch_location",
            "codex_data",
            "codex_readable",
            "database",
            "portability_audit",
            "codex_closed",
            "installation",
            "removable_storage",
            "local_space",
            "recovery_points",
            "local_state",
            "atomic_metadata",
        }.issubset(diagnostic_check_ids)
    )
    package_manifest = backup.read_json(package / "manifest" / "package.json")
    package_portability = backup.read_json(
        package / "reports" / "portability-audit.json"
    )
    package_path_budget = backup.read_json(package / "reports" / "path-budget.json")
    package_portability_audit_complete = bool(
        package_manifest.get("portabilityAudit", {}).get("auditVersion")
        == portability_audit.AUDIT_VERSION
        and package_manifest.get("portabilityAudit", {}).get("status") == "portable"
        and package_portability.get("privacy", {}).get("containsPathValues") is False
        and package_portability.get("summary", {}).get("needsReviewReferences") == 0
    )
    package_path_budget_complete = bool(
        package_path_budget.get("safe") is True
        and package_path_budget.get("longest", {}).get("projectedPath")
        and package_manifest.get("pathBudget", {}).get("reportRelativePath")
        == "reports/path-budget.json"
        and package_manifest.get("pathBudget", {}).get("safe") is True
    )
    git_conflict_explanation, git_advisory_only = _git_conflict_insight_test(root)
    atomic_metadata_complete = _atomic_metadata_test(root)
    checks = {
        "packageValid": package_validation["valid"],
        "visualBackupSummaryComplete": visual_backup_summary_complete,
        "backupSelectionPreviewComplete": backup_selection_preview_complete,
        "rolloutPreflightHasExactDiagnostics": rollout_preflight_diagnostics,
        "destinationPathBudgetPreflight": (
            path_budget_preflight and package_path_budget_complete
        ),
        "singleUsbStillPromptsForDestination": destination_prompt,
        "unreadablePythonCacheWarnsAndContinues": reconstructable_cache_warning,
        "unreadableNormalFileStillFailsClosed": mandatory_copy_failure,
        "identicalDuplicateRolloutResolved": identical_rollout_resolved,
        "differentDuplicateRolloutResolved": different_rollout_resolved,
        "selectiveProjectExclusionComplete": selective_project_exclusion_complete,
        "snapshotUsesSingleFileJournal": snapshot_journal_mode == "delete",
        "validatorIsReadOnly": package_validation.get("checks", {}).get(
            "packageUnchangedDuringValidation", False
        ),
        "hashingProgressComplete": hashing_progress_complete,
        "validationProgressComplete": validation_progress_complete,
        "progressTransitionsClear": progress_transitions_clear,
        "unknownStoreVersionDoesNotWarn": unknown_version_does_not_warn,
        "usbDriveClassification": usb_classification,
        "compressedFolderLaunchBlocked": compressed_launch_detection,
        "diagnosticCenterReadOnlyAndAnonymous": diagnostic_center_complete,
        "pathPortabilityAudit": _path_portability_audit_test(root),
        "backupContainsAnonymousPortabilityAudit": package_portability_audit_complete,
        "gitAwareConflictExplanation": git_conflict_explanation,
        "gitInsightNeverChangesRestoreAction": git_advisory_only,
        "atomicMetadataSurvivesInterruptedWrite": atomic_metadata_complete,
        "strictConversationPrefixClassifier": prefix_classifier_safe,
        "conversationPrefixRejectsUnsafeCases": prefix_classifier_strict,
        "prefixOnlyConversationSyncIsAutomaticAndIdempotent": prefix_sync_automatic,
        "portablePathModel": _portable_path_model_test(),
        "longUnicodePathModel": _long_unicode_path_model_test(),
        "lowDiskSpaceRejected": _low_disk_space_test(),
        "portableLocationsRecorded": portable_locations_recorded,
        "legacyFormat20Supported": supports_format("2.0"),
        "legacyFormat21Supported": supports_format("2.1"),
        "legacyFormat22Supported": supports_format("2.2"),
        "legacyFormat23Supported": supports_format("2.3"),
        "completePhase3Inventory": inventory_complete,
        "attachmentDetectionAndAccessResilience": _attachment_resilience_test(root),
        "pluginRuntimeExcludedAndTargetPreserved": _plugin_runtime_policy_test(root),
        "projectRootInventoryAnalysis": _project_inventory_analysis_test(root),
        "lineageChangeModel": _lineage_model_test(),
        "streamingLineageDigest": _streaming_lineage_digest_test(root),
        "lineageSurvivesRoundTrip": lineage_survives_round_trip,
        "projectLocationMapper": _location_mapper_model_test(root),
        "comparisonPlanPreviewComplete": plan_preview_complete,
        "comparisonPlanPerformsNoWrites": (
            plan_source_before == plan_source_after
            and plan_package_before == plan_package_after
        ),
        "comparisonPlanConflictsBlockRestore": plan_conflicts_block,
        "comparisonPlanMatchesRestoreExecution": planned_actions_match_execution,
        "legacyPackageComparisonSupported": legacy_comparison_supported,
        "conversationConflictChoicesComplete": conversation_choices_complete,
        "conversationMirrorExact": conversation_mirror_exact,
        "repeatedConversationRestoreIsIdempotent": repeated_conversation_idempotent,
        "explicitConversationDelete": explicit_conversation_delete,
        "conversationRollbackPreserved": conversation_rollback_preserved,
        "destinationProjectRetainedByDefault": destination_project_retained_by_default,
        "destinationProjectArchiveComplete": destination_project_archive_complete,
        "destinationProjectDeleteRecoverable": destination_project_delete_recoverable,
        "projectConflictChoicesComplete": project_conflict_choices_complete,
        "destinationProjectRollbackPreserved": destination_project_rollback_preserved,
        "managedRecoveryPointRetention": recovery_retention_complete,
        "restoreUsesManagedRecoveryLocation": managed_recovery_location,
        "transactionalProjectMirror": transactional_mirror_complete,
        "repeatedRestoreIsIdempotent": repeated_restore_idempotent,
        "rollbackAfterProjectQuarantine": quarantine_failure_rollback,
        "rollbackAfterProjectActivation": activation_failure_rollback,
        "projectIdentityModel": _project_identity_model_test(root),
        "projectIdentitiesInstalled": identities_installed,
        "projectIdentitiesSurviveRoundTrip": identities_survive_round_trip,
        "sourceUnchanged": source_before == source_after,
        "sourceAuthExcluded": not source_auth_in_package,
        "portableExecutableIncluded": portable_executable_included,
        "restoreValid": restored_validation["valid"],
        "targetAuthPreserved": auth_preserved,
        "projectExact": project_exact,
        "portableProfileRestored": portable_profile_restored,
        "emptyTreeLineageValidated": package_validation["valid"],
        "missingEmptyTreeRejected": missing_empty_tree_rejected,
        "tamperRejected": tamper_rejected,
        "rollbackTriggeredAndPreserved": rollback_preserved,
        "lineageRollbackPreserved": lineage_rollback_preserved,
        "safetyCopyKept": Path(prepared["safetyRoot"]).is_dir(),
        "newerSourceToOlderTarget": older_schema_restore_valid,
        "stableOperationProgress": _progress_model_test(),
        "dutchEnglishGui": _gui_smoke_test(),
    }
    matrix = compatibility_matrix.build_matrix(checks)
    result = {
        "passed": all(checks.values()),
        "workRoot": str(root),
        "package": str(package),
        "checks": checks,
        "phase11Matrix": matrix,
        "restore": restored,
    }
    backup.write_json(root / "self-test-result.json", result)
    return result
