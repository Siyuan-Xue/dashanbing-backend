#!/usr/bin/env python3
"""Offline, explicit-selection recovery. Never imports application configuration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import time


class RecoveryError(ValueError):
    """A fixed, non-sensitive refusal code, safe to include in CLI JSON."""


def safe_relative(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value) or value.startswith("/")
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise RecoveryError("unsafe_relative_path")
    for part in PurePosixPath(value).parts:
        low = part.lower()
        if (low.startswith(".") or any(word in low for word in ("secret", "credential"))
                or low in ("config", "configs", "configuration", "settings", "env")
                or low.startswith(("config.", "settings."))
                or low.endswith((".env", ".pem", ".key", ".p12", ".pfx", ".ini", ".toml", ".yaml", ".yml"))):
            raise RecoveryError("configuration_or_secret_selection_refused")
    return value


def safe_absolute(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise RecoveryError("explicit_absolute_path_required")
    for component in [*reversed(path.parents), path]:
        if component.is_symlink():
            raise RecoveryError("symlink_path_refused")
    return path


def regular(path: Path):
    safe_absolute(path)
    try:
        info = path.lstat()
    except OSError:
        raise RecoveryError("required_regular_file_unavailable") from None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RecoveryError("links_or_special_files_refused")
    return info


@contextmanager
def read_regular(path: Path):
    before = regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        after = os.fstat(stream.fileno())
        if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or not stat.S_ISREG(after.st_mode) or after.st_nlink != 1):
            raise RecoveryError("source_changed")
        yield stream


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with read_regular(path) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    """No metadata/xattrs, links, or special files are copied."""
    with read_regular(source) as incoming:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())


def inventory(root: Path, selections: list[str]) -> tuple[list[dict], list[str]]:
    files, directories = {}, set()

    def visit(path: Path):
        rel = safe_relative(path.relative_to(root).as_posix())
        safe_absolute(path)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            directories.add(rel)
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            regular(path)
            # Do not accidentally include another unlocked database or its journal.
            files[rel] = {"path": rel, "size": info.st_size, "sha256": sha256(path)}
        for parent in PurePosixPath(rel).parents:
            if str(parent) != ".":
                directories.add(str(parent))

    for selection in selections:
        visit(root / safe_relative(selection))
    names = list(files) + list(directories)
    if len({name.casefold() for name in names}) != len(names):
        raise RecoveryError("ambiguous_path_names")
    return sorted(files.values(), key=lambda item: item["path"]), sorted(directories)


def validate_target(source: Path, target: Path, *, snapshot_target=False):
    safe_absolute(source)
    safe_absolute(target)
    if source == target or source in target.parents or target in source.parents:
        raise RecoveryError("source_target_overlap")
    if not source.is_dir() or not target.parent.is_dir():
        raise RecoveryError("source_and_target_parent_must_exist")
    if target.exists() and (snapshot_target or not target.is_dir() or any(target.iterdir())):
        raise RecoveryError("target_must_be_absent" if snapshot_target else "restore_target_must_be_empty")


def check_database(connection: sqlite3.Connection):
    connection.execute("PRAGMA trusted_schema=OFF")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise RecoveryError("sqlite_integrity_failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RecoveryError("sqlite_foreign_key_failed")


def no_sidecars(database: Path):
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.lexists(str(database) + suffix):
            raise RecoveryError("sqlite_sidecar_requires_offline_checkpoint")


@contextmanager
def offline_database(database: Path):
    regular(database)
    no_sidecars(database)
    # mode=rw never creates a database. Read-only SQLite handles do NOT acquire
    # the required writer exclusion on every platform. No DML is issued here.
    connection = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=0)
    try:
        if connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
            raise RecoveryError("wal_mode_requires_offline_conversion")
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute("PRAGMA query_only=ON")
        no_sidecars(database)
        check_database(connection)
        yield
        no_sidecars(database)
    except sqlite3.Error:
        raise RecoveryError("sqlite_invalid_or_not_quiescent") from None
    finally:
        connection.close()


def validate_payload_database(database: Path):
    regular(database)
    no_sidecars(database)
    try:
        # Only a copied immutable payload is checked with immutable=1.
        with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
            check_database(connection)
    except sqlite3.Error:
        raise RecoveryError("sqlite_invalid") from None


def selection(source: Path, database: str, includes: list[str]):
    safe_relative(database)
    if not includes:
        raise RecoveryError("explicit_file_selections_required")
    files, directories = inventory(source, [database, *includes])
    if database not in {item["path"] for item in files}:
        raise RecoveryError("database_must_be_regular_file")
    for entry in files:
        path = entry["path"]
        if path != database:
            with read_regular(source / path) as stream:
                if stream.read(16) == b"SQLite format 3\x00":
                    raise RecoveryError("multiple_databases_not_supported")
            if path.endswith(("-wal", "-shm", "-journal")):
                raise RecoveryError("sqlite_sidecar_selection_refused")
    return files, directories


def plan(source: Path, target: Path, *, database: str, includes: list[str]) -> dict:
    source, target = safe_absolute(source), safe_absolute(target)
    validate_target(source, target, snapshot_target=True)
    files, directories = selection(source, database, includes)
    return {"status": "planned", "operation": "snapshot", "file_count": len(files),
            "directory_count": len(directories), "bytes": sum(item["size"] for item in files),
            "offline_required": True, "database_checks": "not_run"}


def write_private(path: Path, raw: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def copy_payload(source: Path, target: Path, files: list[dict], directories: list[str]):
    for directory in directories:
        (target / directory).mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in files:
        destination = target / entry["path"]
        copy_file(source / entry["path"], destination)
        if destination.stat().st_size != entry["size"] or sha256(destination) != entry["sha256"]:
            raise RecoveryError("copy_checksum_mismatch")


def sync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(stage: Path, source: Path, target: Path, *, snapshot_target=False):
    validate_target(source, target, snapshot_target=snapshot_target)
    # Bottom-up directory sync and rename: only a completely verified result is
    # published. Rename cannot replace a nonempty directory.
    for root, _, _ in os.walk(stage, topdown=False):
        sync_directory(Path(root))
    os.rename(stage, target)
    sync_directory(target.parent)


def snapshot(source: Path, target: Path, *, database: str, includes: list[str], offline=False, fixture=False):
    started = time.perf_counter()
    if not offline:
        raise RecoveryError("offline_acknowledgment_required")
    source, target = safe_absolute(source), safe_absolute(target)
    validate_target(source, target, snapshot_target=True)
    safe_relative(database)
    stage = None
    try:
        with offline_database(source / database):
            before = selection(source, database, includes)
            stage = Path(tempfile.mkdtemp(prefix=".recovery-", dir=target.parent))
            payload = stage / "payload"
            payload.mkdir(mode=0o700)
            copy_payload(source, payload, *before)
            if before != selection(source, database, includes):
                raise RecoveryError("source_changed_during_snapshot")
            manifest = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                        "consistency": "offline_exclusive_sqlite_lock", "database": database,
                        "files": before[0], "directories": before[1]}
            raw = json.dumps(manifest, sort_keys=True, indent=2).encode()
            write_private(stage / "manifest.json", raw)
            write_private(stage / "manifest.sha256", (hashlib.sha256(raw).hexdigest() + "\n").encode())
            result = verify(stage)
            if before != selection(source, database, includes):
                raise RecoveryError("source_changed_during_snapshot")
            publish(stage, source, target, snapshot_target=True)
        result.update(operation="snapshot", evidence_kind="synthetic_fixture" if fixture else "operator_run")
        if fixture:
            result["wall_seconds"] = time.perf_counter() - started
        return result
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)


def read_manifest(source: Path) -> dict:
    safe_absolute(source)
    if not source.is_dir() or {p.name for p in source.iterdir()} != {"manifest.json", "manifest.sha256", "payload"}:
        raise RecoveryError("invalid_snapshot_layout")
    with read_regular(source / "manifest.json") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise RecoveryError("manifest_too_large")
    with read_regular(source / "manifest.sha256") as stream:
        expected = stream.read(66).strip()
    if expected != hashlib.sha256(raw).hexdigest().encode():
        raise RecoveryError("manifest_checksum_mismatch")
    try:
        manifest = json.loads(raw)
        if (manifest["format_version"] != 1 or manifest["consistency"] != "offline_exclusive_sqlite_lock"
                or not isinstance(manifest["files"], list) or not isinstance(manifest["directories"], list)):
            raise ValueError
        safe_relative(manifest["database"])
        names = []
        for entry in manifest["files"]:
            names.append(safe_relative(entry["path"]))
            if (type(entry["size"]) is not int or entry["size"] < 0
                    or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])):
                raise ValueError
        if manifest["database"] not in names:
            raise ValueError
        names += [safe_relative(path) for path in manifest["directories"]]
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError
        return manifest
    except (ValueError, TypeError, KeyError):
        raise RecoveryError("invalid_manifest") from None


def verified_manifest(source: Path):
    manifest = read_manifest(source)
    payload = safe_absolute(source / "payload")
    if not payload.is_dir():
        raise RecoveryError("invalid_snapshot_payload")
    actual = inventory(payload, [item.name for item in payload.iterdir()])
    expected = (sorted(manifest["files"], key=lambda item: item["path"]), sorted(manifest["directories"]))
    if actual != expected:
        raise RecoveryError("snapshot_checksum_or_inventory_mismatch")
    validate_payload_database(payload / manifest["database"])
    return manifest


def verify(source: Path):
    manifest = verified_manifest(safe_absolute(source))
    return {"status": "verified", "file_count": len(manifest["files"]),
            "sqlite_integrity": "ok", "sqlite_foreign_keys": "ok"}


def restore(source: Path, target: Path, *, offline=False):
    if not offline:
        raise RecoveryError("offline_acknowledgment_required")
    source, target = safe_absolute(source), safe_absolute(target)
    validate_target(source, target)
    manifest = verified_manifest(source)
    stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=target.parent))
    try:
        copy_payload(source / "payload", stage, manifest["files"], manifest["directories"])
        validate_payload_database(stage / manifest["database"])
        if manifest != verified_manifest(source):
            raise RecoveryError("snapshot_changed_during_restore")
        publish(stage, source, target)
        return {"status": "restored", "operation": "restore", "file_count": len(manifest["files"]),
                "sqlite_integrity": "ok", "sqlite_foreign_keys": "ok"}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def rollback(source: Path, target: Path, *, offline=False):
    result = restore(source, target, offline=offline)
    result["operation"] = "rollback"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("plan", "snapshot", "verify", "restore", "rollback"):
        sub = commands.add_parser(name)
        sub.add_argument("--source", type=Path, required=True)
        if name != "verify":
            sub.add_argument("--target", type=Path, required=True)
            sub.add_argument("--dry-run", action="store_true")
        if name in ("plan", "snapshot"):
            sub.add_argument("--database", required=True, help="Relative SQLite file in source")
            sub.add_argument("--include", action="append", required=True, help="Explicit relative file/directory; repeatable")
        if name in ("snapshot", "restore", "rollback"):
            sub.add_argument("--offline", action="store_true", help="Attest queues drained and ALL writers stopped externally")
        if name == "snapshot":
            sub.add_argument("--fixture", action="store_true", help="Attest synthetic-only input; include fixture timing")
    args = parser.parse_args(argv)
    try:
        if args.operation in ("plan", "snapshot"):
            kwargs = dict(database=args.database, includes=args.include)
            if args.operation == "plan" or args.dry_run:
                result = plan(args.source, args.target, **kwargs)
            else:
                result = snapshot(args.source, args.target, offline=args.offline, fixture=args.fixture, **kwargs)
        elif args.operation == "verify":
            result = verify(args.source)
        elif args.dry_run:
            validate_target(args.source, args.target)
            result = verify(args.source)
            result.update(status="planned", operation=args.operation, offline_required=True)
        else:
            operation = rollback if args.operation == "rollback" else restore
            result = operation(args.source, args.target, offline=args.offline)
    except (RecoveryError, OSError, sqlite3.Error) as error:
        # No path, SQL content, manifest value, or exception text is echoed.
        code = str(error) if isinstance(error, RecoveryError) else "io_or_sqlite_error"
        print(json.dumps({"status": "refused", "error": code}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
