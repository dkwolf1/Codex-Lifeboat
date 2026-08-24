"""Read-only Git evidence for explaining project conflicts."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


INSIGHT_VERSION = 1


def _run(
    root: Path, *arguments: str, alternate_objects: tuple[Path, ...] = ()
) -> tuple[int, str]:
    executable = shutil.which("git")
    if not executable:
        return 127, ""
    try:
        environment = os.environ.copy()
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        if alternate_objects:
            existing = environment.get("GIT_ALTERNATE_OBJECT_DIRECTORIES")
            values = [str(path) for path in alternate_objects]
            if existing:
                values.append(existing)
            environment["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.pathsep.join(values)
        completed = subprocess.run(
            [executable, "--no-optional-locks", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return 126, ""
    return completed.returncode, completed.stdout.strip()


def inspect_repository(root: Path | None) -> dict[str, Any]:
    """Collect path-free repository state without changing the worktree."""

    if root is None or not root.is_dir() or not (root / ".git").exists():
        return {"available": False, "reason": "not-a-git-worktree"}
    code, inside = _run(root, "rev-parse", "--is-inside-work-tree")
    if code or inside.casefold() != "true":
        return {"available": False, "reason": "git-unavailable-or-invalid"}
    head_code, head = _run(root, "rev-parse", "--verify", "HEAD")
    status_code, status = _run(
        root, "status", "--porcelain=v1", "--untracked-files=normal"
    )
    status_lines = [line for line in status.splitlines() if line]
    return {
        "available": head_code == 0 and len(head) == 40,
        "reason": None if head_code == 0 else "repository-has-no-head",
        "head": head if head_code == 0 else None,
        "dirty": bool(status_lines) if status_code == 0 else None,
        "changedEntries": len(status_lines) if status_code == 0 else None,
    }


def _object_directory(root: Path) -> Path | None:
    code, value = _run(root, "rev-parse", "--git-path", "objects")
    if code or not value:
        return None
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve(strict=False)


def _commit_exists(root: Path, commit: str, alternates: tuple[Path, ...]) -> bool:
    return _run(
        root, "cat-file", "-e", f"{commit}^{{commit}}", alternate_objects=alternates
    )[0] == 0


def _is_ancestor(
    root: Path, older: str, newer: str, alternates: tuple[Path, ...]
) -> bool:
    return _run(
        root, "merge-base", "--is-ancestor", older, newer,
        alternate_objects=alternates,
    )[0] == 0


def compare_repositories(source_root: Path, target_root: Path | None) -> dict[str, Any]:
    """Explain Git history relationship; never select or perform a restore action."""

    source = inspect_repository(source_root)
    target = inspect_repository(target_root)
    result: dict[str, Any] = {
        "gitInsightVersion": INSIGHT_VERSION,
        "classification": "insufficient-evidence",
        "historyRelation": "unknown",
        "sourceAvailable": bool(source.get("available")),
        "targetAvailable": bool(target.get("available")),
        "sourceDirty": source.get("dirty"),
        "targetDirty": target.get("dirty"),
        "sourceChangedEntries": source.get("changedEntries"),
        "targetChangedEntries": target.get("changedEntries"),
        "automaticActionChanged": False,
    }
    if not source.get("available") or not target.get("available") or target_root is None:
        return result
    source_head = str(source["head"])
    target_head = str(target["head"])
    if source_head == target_head:
        result["historyRelation"] = "same-commit"
        result["classification"] = (
            "exact-git-state"
            if not source.get("dirty") and not target.get("dirty")
            else "same-commit-working-tree-differs"
        )
        return result
    comparison_root = source_root
    target_objects = _object_directory(target_root)
    alternates = (target_objects,) if target_objects else ()
    if not _commit_exists(comparison_root, source_head, alternates) or not _commit_exists(
        comparison_root, target_head, alternates
    ):
        result["historyRelation"] = "unrelated-or-unavailable"
        return result
    if _is_ancestor(comparison_root, target_head, source_head, alternates):
        result["historyRelation"] = "backup-ahead"
        result["classification"] = "explainable-forward-progress"
    elif _is_ancestor(comparison_root, source_head, target_head, alternates):
        result["historyRelation"] = "computer-ahead"
        result["classification"] = "explainable-forward-progress"
    elif _run(
        comparison_root, "merge-base", source_head, target_head,
        alternate_objects=alternates,
    )[0] == 0:
        result["historyRelation"] = "diverged"
        result["classification"] = "true-divergence"
    else:
        result["historyRelation"] = "unrelated"
    return result
