"""Shared streaming support for plain and Zstandard-compressed rollouts."""

from __future__ import annotations

import contextlib
import codecs
import io
from pathlib import Path
from typing import Iterator, TextIO

import zstandard


PLAIN_SUFFIX = ".jsonl"
COMPRESSED_SUFFIX = ".jsonl.zst"
READ_ERRORS = (OSError, UnicodeError, zstandard.ZstdError)
_COMPRESSED_INPUT_CHUNK = 16 * 1024


def is_rollout_path(path: Path | str) -> bool:
    """Return whether a path uses a supported Codex rollout filename."""

    name = Path(path).name.casefold()
    return name.endswith(PLAIN_SUFFIX) or name.endswith(COMPRESSED_SUFFIX)


def is_compressed(path: Path | str) -> bool:
    return Path(path).name.casefold().endswith(COMPRESSED_SUFFIX)


def iter_files(root: Path) -> Iterator[Path]:
    """Yield supported rollout files below root."""

    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if path.is_file() and is_rollout_path(path):
            yield path


def _validated_decompressed_chunks(path: Path) -> Iterator[bytes]:
    """Yield bounded decompressed chunks and reject incomplete/invalid frames."""

    pending = b""
    with path.open("rb") as raw:
        while True:
            decompressor = zstandard.ZstdDecompressor().decompressobj()
            while not decompressor.eof:
                data = pending or raw.read(_COMPRESSED_INPUT_CHUNK)
                pending = b""
                if not data:
                    raise zstandard.ZstdError(
                        "compressed rollout ended before the Zstandard frame completed"
                    )
                decoded = decompressor.decompress(data)
                if decoded:
                    yield decoded
                pending = decompressor.unused_data
            if not pending:
                pending = raw.read(_COMPRESSED_INPUT_CHUNK)
            if not pending:
                return


def read_first_line(path: Path) -> str:
    """Read metadata and fully validate compressed frames in one streaming pass."""

    if not is_compressed(path):
        with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
            return handle.readline()

    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    first_line = ""
    complete = False
    for chunk in _validated_decompressed_chunks(path):
        text = decoder.decode(chunk)
        if not complete:
            before, separator, _after = text.partition("\n")
            first_line += before
            complete = bool(separator)
    tail = decoder.decode(b"", final=True)
    if not complete:
        first_line += tail.partition("\n")[0]
    return first_line + ("\n" if complete else "")


@contextlib.contextmanager
def open_text(
    path: Path,
    *,
    errors: str = "strict",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """Open rollout content as UTF-8 text, decompressing Zstandard on the fly."""

    if not is_compressed(path):
        with path.open(
            "r", encoding="utf-8-sig", errors=errors, newline=newline
        ) as handle:
            yield handle
        return

    with path.open("rb") as raw:
        with zstandard.ZstdDecompressor().stream_reader(
            raw, read_across_frames=True
        ) as decompressed:
            with io.TextIOWrapper(
                decompressed,
                encoding="utf-8-sig",
                errors=errors,
                newline=newline,
            ) as text:
                yield text


@contextlib.contextmanager
def open_text_writer(path: Path, *, newline: str = "\n") -> Iterator[TextIO]:
    """Create rollout text while preserving the destination compression type."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not is_compressed(path):
        with path.open("w", encoding="utf-8", newline=newline) as handle:
            yield handle
        return

    with path.open("wb") as raw:
        with zstandard.ZstdCompressor().stream_writer(raw) as compressed:
            with io.TextIOWrapper(
                compressed, encoding="utf-8", newline=newline
            ) as text:
                yield text
