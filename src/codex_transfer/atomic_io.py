"""Durable same-directory replacement for Lifeboat metadata files."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable


ATOMIC_METADATA_VERSION = 1
HARDENED_STORES = (
    "backup manifests and reports",
    "backup and GUI configuration",
    "diagnostic support reports",
    "project identity registry",
    "backup lineage and device state",
    "external location mappings",
    "restore journals",
)


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")


def _sync_parent(path: Path) -> None:
    """Best-effort directory flush; Windows does not expose this uniformly."""

    flags = getattr(os, "O_RDONLY", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path.parent, flags | directory_flag)
    except (AttributeError, OSError, TypeError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    validate: Callable[[str], None] | None = None,
) -> None:
    """Write complete metadata, validate it, then atomically replace the target."""

    path = Path(path).resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        with temporary.open("x", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        persisted = temporary.read_text(encoding=encoding)
        if persisted != text:
            raise OSError(f"Temporary metadata verification failed: {path.name}")
        if validate:
            validate(persisted)
        os.replace(temporary, path)
        _sync_parent(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def write_json(
    path: Path,
    value: Any,
    *,
    validate: Callable[[Any], None] | None = None,
) -> None:
    """Serialize, parse-check, optionally validate, and atomically replace JSON."""

    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"

    def validate_text(persisted: str) -> None:
        parsed = json.loads(persisted)
        if validate:
            validate(parsed)

    write_text(path, text, validate=validate_text)
