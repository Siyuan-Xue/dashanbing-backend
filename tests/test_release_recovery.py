"""Recovery tests use newly created SQLite/files only; no deployment imports."""
import hashlib
import importlib
import json
import os
import sqlite3

import pytest


@pytest.fixture
def recovery():
    return importlib.import_module("scripts.release_recovery")


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    with sqlite3.connect(root / "data.sqlite") as db:
        db.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY);"
                         "CREATE TABLE child(id INTEGER REFERENCES parent(id));"
                         "INSERT INTO parent VALUES(1); INSERT INTO child VALUES(1);")
    (root / "files" / "empty").mkdir(parents=True)
    (root / "files" / "item.json").write_text('{"fixture": true}')
    # An unselected synthetic secret must never be read or copied.
    (root / ".env").write_text("FAKE_SECRET=never-print-this")
    return root


def snapshot(recovery, source, target, **kwargs):
    return recovery.snapshot(source, target, database="data.sqlite", includes=["files"],
                             offline=True, fixture=True, **kwargs)


def test_plan_has_no_writes_and_requires_explicit_selection(recovery, source, tmp_path):
    target = tmp_path / "backup"
    result = recovery.plan(source, target, database="data.sqlite", includes=["files"])
    assert result["status"] == "planned"
    assert not target.exists()
    assert "never-print-this" not in json.dumps(result)
    with pytest.raises(recovery.RecoveryError):
        recovery.snapshot(source, target, database="data.sqlite", includes=["files"], offline=False)
    assert not target.exists()


def test_snapshot_verify_restore_and_rollback(recovery, source, tmp_path):
    backup = tmp_path / "backup"
    result = snapshot(recovery, source, backup)
    assert result["status"] == "verified"
    assert result["evidence_kind"] == "synthetic_fixture"
    assert result["wall_seconds"] >= 0
    assert recovery.verify(backup)["status"] == "verified"
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["database"] == "data.sqlite"
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert not (backup / "payload" / ".env").exists()
    restored = tmp_path / "restored"
    restored.mkdir()
    recovery.restore(backup, restored, offline=True)
    assert (restored / "files" / "empty").is_dir()
    with sqlite3.connect(restored / "data.sqlite") as db:
        assert db.execute("SELECT * FROM child").fetchall() == [(1,)]
    (restored / "files" / "item.json").write_text("new-release-data")
    rollback = tmp_path / "rollback"
    recovery.rollback(backup, rollback, offline=True)
    assert (rollback / "files" / "item.json").read_text() == '{"fixture": true}'
    assert (restored / "files" / "item.json").read_text() == "new-release-data"


def test_corruption_and_nonempty_target_refused(recovery, source, tmp_path):
    backup = tmp_path / "backup"
    snapshot(recovery, source, backup)
    target = tmp_path / "restore"
    target.mkdir()
    (target / "keep").write_text("keep")
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(backup, target, offline=True)
    assert (target / "keep").read_text() == "keep"
    (backup / "payload" / "files" / "item.json").write_text("corrupt")
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(backup, tmp_path / "fresh", offline=True)
    assert not (tmp_path / "fresh").exists()


@pytest.mark.parametrize("entry", ["../escape", "/tmp/escape", "files/../data.sqlite", "files\\escape", ".env", ".", "files/config.yaml"])
def test_unsafe_selection_refused(recovery, source, tmp_path, entry):
    with pytest.raises(recovery.RecoveryError):
        recovery.snapshot(source, tmp_path / "backup", database="data.sqlite", includes=[entry], offline=True)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_special_files_refused(recovery, source, tmp_path, kind):
    path = source / "files" / "unsafe"
    if kind == "symlink":
        path.symlink_to(source / ".env")
    elif kind == "hardlink":
        os.link(source / ".env", path)
    else:
        os.mkfifo(path)
    with pytest.raises(recovery.RecoveryError):
        snapshot(recovery, source, tmp_path / "backup")


def test_symlink_parent_and_overlapping_target_refused(recovery, source, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(recovery.RecoveryError):
        snapshot(recovery, link, tmp_path / "backup")
    with pytest.raises(recovery.RecoveryError):
        snapshot(recovery, source, source / "backup")


@pytest.mark.parametrize("fault", ["fk", "invalid_db", "wal", "writer"])
def test_database_safety_checks(recovery, source, tmp_path, fault):
    db = None
    if fault == "fk":
        with sqlite3.connect(source / "data.sqlite") as con:
            con.execute("INSERT INTO child VALUES(999)")
    elif fault == "invalid_db":
        (source / "data.sqlite").write_bytes(b"not a database")
    elif fault == "wal":
        (source / "data.sqlite-wal").write_bytes(b"pending")
    else:
        db = sqlite3.connect(source / "data.sqlite")
        db.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(recovery.RecoveryError):
            snapshot(recovery, source, tmp_path / "backup")
        assert not (tmp_path / "backup").exists()
    finally:
        if db is not None:
            db.close()


@pytest.mark.parametrize("fault", ["traversal", "extra", "link", "fk"])
def test_untrusted_snapshot_refused_even_with_rehashed_manifest(recovery, source, tmp_path, fault):
    backup = tmp_path / "backup"
    snapshot(recovery, source, backup)
    manifest = json.loads((backup / "manifest.json").read_text())
    if fault == "traversal":
        manifest["files"][0]["path"] = "../escape"
    elif fault == "extra":
        (backup / "payload" / "extra").write_text("not manifested")
    elif fault == "link":
        path = backup / "payload" / "files" / "item.json"
        path.unlink()
        path.symlink_to(source / ".env")
    else:
        path = backup / "payload" / "data.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO child VALUES(999)")
        entry = next(item for item in manifest["files"] if item["path"] == "data.sqlite")
        entry.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    raw = json.dumps(manifest).encode()
    (backup / "manifest.json").write_bytes(raw)
    (backup / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(backup, tmp_path / "restored", offline=True)
    assert not (tmp_path / "restored").exists()


def test_changes_during_snapshot_are_not_published(recovery, source, tmp_path, monkeypatch):
    original = recovery.copy_file

    def mutate(src, dst):
        original(src, dst)
        if src.name == "item.json":
            src.write_text("writer-was-not-stopped")

    monkeypatch.setattr(recovery, "copy_file", mutate)
    with pytest.raises(recovery.RecoveryError):
        snapshot(recovery, source, tmp_path / "backup")
    assert not (tmp_path / "backup").exists()


def test_snapshot_holds_writer_lock_and_leaves_source_bytes_unchanged(recovery, source, tmp_path, monkeypatch):
    original = recovery.copy_file
    before = (source / "data.sqlite").read_bytes()
    blocked = []

    def competing_writer(src, dst):
        with sqlite3.connect(source / "data.sqlite", timeout=0) as db:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                db.execute("INSERT INTO parent VALUES(2)")
            blocked.append(True)
        original(src, dst)

    monkeypatch.setattr(recovery, "copy_file", competing_writer)
    snapshot(recovery, source, tmp_path / "backup")
    assert blocked
    assert (source / "data.sqlite").read_bytes() == before


def test_rollback_dry_run_and_missing_offline_do_not_write(recovery, source, tmp_path, capsys):
    backup = tmp_path / "backup"
    snapshot(recovery, source, backup)
    target = tmp_path / "rollback"
    args = ["rollback", "--source", str(backup), "--target", str(target)]
    assert recovery.main([*args, "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "planned"
    assert not target.exists()
    with pytest.raises(recovery.RecoveryError):
        recovery.rollback(backup, target)
    assert not target.exists()


def test_unknown_database_and_second_database_are_refused(recovery, source, tmp_path):
    with pytest.raises(recovery.RecoveryError):
        recovery.snapshot(source, tmp_path / "backup", database="missing.sqlite", includes=["files"], offline=True)
    with sqlite3.connect(source / "files" / "second.data") as db:
        db.execute("CREATE TABLE other(id INTEGER)")
    with pytest.raises(recovery.RecoveryError):
        snapshot(recovery, source, tmp_path / "backup")


@pytest.mark.parametrize("text", ['{}', 'null', '[1]', '{"format_version": 1}', '\ud800'])
def test_malformed_manifest_fails_closed(recovery, source, tmp_path, text):
    backup = tmp_path / "backup"
    snapshot(recovery, source, backup)
    raw = text.encode("utf-8", errors="surrogatepass")
    (backup / "manifest.json").write_bytes(raw)
    (backup / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    with pytest.raises(recovery.RecoveryError):
        recovery.verify(backup)


def test_cli_errors_do_not_echo_config_values(recovery, source, tmp_path, capsys):
    code = recovery.main(["snapshot", "--source", str(source), "--target", str(tmp_path / "backup"),
                          "--database", "data.sqlite", "--include", ".env", "--offline"])
    output = capsys.readouterr()
    assert code == 2
    assert "never-print-this" not in output.out + output.err
    assert json.loads(output.out)["status"] == "refused"
