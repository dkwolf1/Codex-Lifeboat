"""Strict, read-only proof of safe prefix-only conversation synchronization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from . import lineage


PREFIX_VERSION = 1


class ConversationRecordError(ValueError):
    """Raised when a rollout cannot be compared as semantic JSONL records."""


def _canonical_records(
    path: Path, replacements: list[tuple[str, str]]
) -> Iterator[str]:
    first_line = True
    with path.open("rb") as handle:
        for number, raw_line in enumerate(handle, start=1):
            try:
                line = raw_line.decode("utf-8-sig" if first_line else "utf-8")
            except UnicodeError as exc:
                raise ConversationRecordError(
                    f"rollout is not valid UTF-8 at record {number}"
                ) from exc
            first_line = False
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConversationRecordError(
                    f"rollout contains invalid JSON at record {number}"
                ) from exc
            normalized = lineage.normalize_semantic_value(value, replacements)
            yield json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )


def _metadata_equal(
    source: Any,
    target: Any,
    source_replacements: list[tuple[str, str]],
    target_replacements: list[tuple[str, str]],
) -> bool:
    return lineage.normalize_semantic_value(source, source_replacements) == (
        lineage.normalize_semantic_value(target, target_replacements)
    )


def compare(
    source_path: Path,
    target_path: Path,
    source_replacements: list[tuple[str, str]],
    target_replacements: list[tuple[str, str]],
    source_metadata: Any,
    target_metadata: Any,
) -> dict[str, Any]:
    """Prove whether target is an unchanged, non-empty prefix of source.

    No rollout is modified. The result deliberately contains counts and reason codes,
    never chat content or paths.
    """

    result: dict[str, Any] = {
        "prefixVersion": PREFIX_VERSION,
        "relation": "unavailable",
        "automatic": False,
        "matchedRecords": 0,
        "targetRecords": None,
        "sourceRecords": None,
        "additionalSourceRecords": 0,
    }
    if not source_path.is_file() or not target_path.is_file():
        result["reason"] = "rollout-unavailable"
        return result
    if not _metadata_equal(
        source_metadata,
        target_metadata,
        source_replacements,
        target_replacements,
    ):
        result.update(relation="metadata-conflict", reason="metadata-differs")
        return result

    source_records = _canonical_records(source_path, source_replacements)
    target_records = _canonical_records(target_path, target_replacements)
    matched = 0
    try:
        while True:
            try:
                target_record = next(target_records)
            except StopIteration:
                break
            try:
                source_record = next(source_records)
            except StopIteration:
                target_count = matched + 1
                for _record in target_records:
                    target_count += 1
                result.update(
                    relation="source-prefix",
                    reason="destination-is-longer",
                    matchedRecords=matched,
                    targetRecords=target_count,
                    sourceRecords=matched,
                )
                return result
            if source_record != target_record:
                result.update(
                    relation="diverged",
                    reason="existing-record-differs",
                    matchedRecords=matched,
                )
                return result
            matched += 1

        additional = 0
        for _record in source_records:
            additional += 1
        source_count = matched + additional
        if additional == 0:
            result.update(
                relation="equal",
                reason="same-records",
                matchedRecords=matched,
                targetRecords=matched,
                sourceRecords=source_count,
            )
            return result
        if matched == 0:
            result.update(
                relation="empty-target",
                reason="empty-destination-is-not-auto-synced",
                matchedRecords=0,
                targetRecords=0,
                sourceRecords=source_count,
                additionalSourceRecords=additional,
            )
            return result
        result.update(
            relation="target-prefix",
            reason="exact-prefix",
            automatic=True,
            matchedRecords=matched,
            targetRecords=matched,
            sourceRecords=source_count,
            additionalSourceRecords=additional,
        )
        return result
    except (OSError, ConversationRecordError):
        result.update(
            relation="invalid",
            reason="unreadable-or-invalid-jsonl",
            matchedRecords=matched,
        )
        return result
