"""Opt-in, read-only-source SQLite snapshot helper for private rehearsal data.

This module is never invoked by pytest or application startup. All paths are
mandatory. Destination and manifest parents must be run-owned mode-0700 dirs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import threading
from pathlib import Path
from typing import Callable


_UMASK_LOCK = threading.Lock()
_SIDECARS = ("-journal", "-wal", "-shm")


def _exists_entry(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _same_file_or_path(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    if _exists_entry(left) and _exists_entry(right):
        try:
            return os.path.samefile(left, right)
        except OSError:
            return False
    return False


def _check_private_parent(path: Path) -> None:
    try:
        info = path.parent.lstat()
    except FileNotFoundError as exc:
        raise ValueError("private parent directory must already exist") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("private parent must be a real directory, not a symlink")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private parent must be run-owned and mode 0700")


def _reserve_private_file(path: Path) -> int:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        os.close(fd)
        raise ValueError("private output must be a run-owned regular mode-0600 file")
    return fd


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_database(source_uri: str, destination: Path) -> tuple[str | None, list[str], int]:
    src = None
    dst = None
    try:
        src = sqlite3.connect(source_uri, uri=True)
        dst = sqlite3.connect(destination)
        src.backup(dst)
        revision_row = dst.execute("SELECT version_num FROM alembic_version").fetchone()
        integrity = [row[0] for row in dst.execute("PRAGMA integrity_check")]
        fk_count = sum(1 for _ in dst.execute("PRAGMA foreign_key_check"))
        return (revision_row[0] if revision_row else None, integrity, fk_count)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()


def _unlink_owned(path: Path, inode: int | None) -> None:
    if inode is None:
        return
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_ino == inode:
        path.unlink()


def snapshot(
    source: Path,
    destination: Path,
    output: Path,
    *,
    copy_database: Callable[[str, Path], tuple[str | None, list[str], int]] | None = None,
) -> dict[str, object]:
    if copy_database is None:
        copy_database = _copy_database
    source, destination, output = (p.expanduser().absolute() for p in (source, destination, output))
    if not source.is_file():
        raise ValueError("source must be an existing regular file")
    if _same_file_or_path(source, destination):
        raise ValueError("source and destination must be different files")
    if _same_file_or_path(source, output) or _same_file_or_path(destination, output):
        raise ValueError("output manifest must be separate from source and destination")
    _check_private_parent(destination)
    _check_private_parent(output)
    if _exists_entry(destination) or _exists_entry(output):
        raise ValueError("destination and output must not already exist")
    sidecars = [Path(f"{destination}{suffix}") for suffix in _SIDECARS]
    if any(_exists_entry(path) for path in sidecars):
        raise ValueError("destination has a pre-existing SQLite sidecar")

    source_hash_before = _source_hash(source)
    owned: dict[Path, int] = {}
    descriptors: list[int] = []
    try:
        db_fd = _reserve_private_file(destination)
        descriptors.append(db_fd)
        owned[destination] = os.fstat(db_fd).st_ino
        output_fd = _reserve_private_file(output)
        descriptors.append(output_fd)
        owned[output] = os.fstat(output_fd).st_ino

        # SQLite may create rollback/WAL sidecars while writing. Restrict their
        # mode at creation; private parent directories provide an additional
        # access-control boundary. Serialize the process-global umask change.
        source_uri = source.as_uri() + "?mode=ro"
        with _UMASK_LOCK:
            old_umask = os.umask(0o077)
            try:
                revision, integrity, fk_count = copy_database(source_uri, destination)
            finally:
                os.umask(old_umask)
        if _source_hash(source) != source_hash_before:
            raise ValueError("source changed during snapshot acquisition")

        manifest: dict[str, object] = {
            "source_sha256": source_hash_before,
            "source_revision": revision,
            "snapshot_sha256": _source_hash(destination),
            "integrity_check": integrity,
            "foreign_key_violation_count": fk_count,
        }
        with os.fdopen(output_fd, "w", encoding="utf-8", closefd=False) as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return manifest
    except BaseException:
        # Close all SQLite/file descriptors before removing only inode-verified
        # files reserved by this invocation. Never unlink a competing artifact.
        for fd in descriptors:
            try:
                os.close(fd)
            except OSError:
                pass
        descriptors.clear()
        for path, inode in owned.items():
            _unlink_owned(path, inode)
        raise
    finally:
        for fd in descriptors:
            try:
                os.close(fd)
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--copy", required=True, type=Path, dest="destination")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source, args.destination, args.output), indent=2))


if __name__ == "__main__":
    main()
