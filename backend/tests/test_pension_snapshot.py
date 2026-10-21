import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts import pension_snapshot
from scripts.pension_snapshot import snapshot


BASELINE = "0dea247bc8ed465b0d85da60fe6c0a4804ff085e"


@contextmanager
def _connect(path: Path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _database(path: Path) -> None:
    with _connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT)")
        connection.execute("INSERT INTO alembic_version VALUES ('synthetic')")


def _private_dir(tmp_path: Path, name: str = "private") -> Path:
    path = tmp_path / name
    path.mkdir()
    path.chmod(0o700)
    return path


def test_snapshot_rejects_source_equal_to_destination(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    _database(source)
    before = source.read_bytes()

    with pytest.raises(ValueError, match="source and destination"):
        snapshot(source, source, private / "manifest.json")
    assert source.read_bytes() == before


def test_snapshot_rejects_source_alias_destination(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    alias = private / "alias.db"
    _database(source)
    alias.symlink_to(source)
    before = source.read_bytes()

    with pytest.raises(ValueError, match="source and destination"):
        snapshot(source, alias, private / "manifest.json")
    assert source.read_bytes() == before


def test_snapshot_rejects_dangling_destination_and_output_symlinks(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    _database(source)
    before = source.read_bytes()
    dangling_destination = private / "dangling-destination"
    dangling_destination.symlink_to(private / "missing-db")
    with pytest.raises(ValueError, match="already exist"):
        snapshot(source, dangling_destination, private / "report.json")
    assert dangling_destination.is_symlink()
    assert source.read_bytes() == before

    dangling_output = private / "dangling-output"
    dangling_output.symlink_to(private / "missing-report")
    destination = private / "copy.db"
    with pytest.raises(ValueError, match="already exist"):
        snapshot(source, destination, dangling_output)
    assert dangling_output.is_symlink()
    assert not destination.exists()
    assert source.read_bytes() == before


def test_snapshot_rejects_hardlinked_output_identity(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    _database(source)
    output = private / "source-hardlink"
    os.link(source, output)
    before = source.read_bytes()

    with pytest.raises(ValueError, match="separate from source"):
        snapshot(source, private / "copy.db", output)
    assert output.exists()
    assert source.read_bytes() == before


def test_snapshot_rejects_non_private_parent_even_with_permissive_umask(tmp_path: Path) -> None:
    private = tmp_path / "permissive"
    private.mkdir(mode=0o777)
    private.chmod(0o755)
    source = tmp_path / "source.db"
    _database(source)
    previous = os.umask(0)
    try:
        with pytest.raises(ValueError, match="mode 0700"):
            snapshot(source, private / "copy.db", private / "report.json")
    finally:
        os.umask(previous)
    assert not (private / "copy.db").exists()


def test_snapshot_creates_private_files_before_backup_and_restricts_sidecars(tmp_path: Path, monkeypatch) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    destination = private / "copy.db"
    output = private / "report.json"
    _database(source)
    observed = {}
    real_copy = pension_snapshot._copy_database

    def inspect_copy(source_uri: str, copy_path: Path):
        observed["copy_mode"] = copy_path.stat().st_mode & 0o777
        observed["output_mode"] = output.stat().st_mode & 0o777
        sidecar = Path(f"{copy_path}-journal")
        fd = os.open(sidecar, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        os.close(fd)
        observed["sidecar_mode"] = sidecar.stat().st_mode & 0o777
        sidecar.unlink()
        return real_copy(source_uri, copy_path)

    monkeypatch.setattr(pension_snapshot, "_copy_database", inspect_copy)
    previous = os.umask(0)
    try:
        result = snapshot(source, destination, output)
    finally:
        os.umask(previous)

    assert observed == {"copy_mode": 0o600, "output_mode": 0o600, "sidecar_mode": 0o600}
    assert result["source_revision"] == "synthetic"
    assert result["integrity_check"] == ["ok"]
    assert destination.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o600


def test_snapshot_failure_closes_and_removes_only_owned_artifacts(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    destination = private / "copy.db"
    output = private / "report.json"
    other = private / "other.txt"
    _database(source)
    before = source.read_bytes()
    other.write_text("preserve", encoding="utf-8")

    def fail_after_sqlite_handles_close(source_uri: str, copy_path: Path):
        revision, integrity, fk = pension_snapshot._copy_database(source_uri, copy_path)
        assert copy_path.stat().st_mode & 0o777 == 0o600
        raise OSError("injected post-backup failure")

    with pytest.raises(OSError, match="injected"):
        snapshot(source, destination, output, copy_database=fail_after_sqlite_handles_close)
    assert not destination.exists()
    assert not output.exists()
    assert other.read_text(encoding="utf-8") == "preserve"
    assert source.read_bytes() == before


def test_snapshot_preserves_competing_output_created_during_reservation(tmp_path: Path, monkeypatch) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    destination = private / "copy.db"
    output = private / "report.json"
    _database(source)
    before = source.read_bytes()
    real_reserve = pension_snapshot._reserve_private_file

    def race_reserve(path: Path):
        if path == output:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, b"other writer")
            os.close(fd)
        return real_reserve(path)

    monkeypatch.setattr(pension_snapshot, "_reserve_private_file", race_reserve)
    with pytest.raises(FileExistsError):
        snapshot(source, destination, output)
    assert output.read_bytes() == b"other writer"
    assert not destination.exists()
    assert source.read_bytes() == before


def test_snapshot_output_write_failure_removes_only_its_files(tmp_path: Path, monkeypatch) -> None:
    private = _private_dir(tmp_path)
    source, destination, output = private / "source.db", private / "copy.db", private / "report.json"
    _database(source)
    source_before = source.read_bytes()

    def fail_json(*_args, **_kwargs):
        raise OSError("injected manifest write failure")

    monkeypatch.setattr(pension_snapshot.json, "dump", fail_json)
    with pytest.raises(OSError, match="manifest write"):
        snapshot(source, destination, output)
    assert not destination.exists()
    assert not output.exists()
    assert source.read_bytes() == source_before


def test_snapshot_failure_removes_only_its_reservation_and_sidecar(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    destination = private / "copy.db"
    output = private / "report.json"
    other_sidecar = Path(f"{destination}-journal")
    _database(source)
    before = source.read_bytes()

    def fail_with_owned_sidecar(source_uri: str, copy_path: Path):
        fd = os.open(other_sidecar, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        assert other_sidecar.stat().st_mode & 0o777 == 0o600
        # Simulates SQLite cleaning its own sidecar when its connection closes.
        other_sidecar.unlink()
        raise RuntimeError("injected backup failure")

    with pytest.raises(RuntimeError, match="injected"):
        snapshot(source, destination, output, copy_database=fail_with_owned_sidecar)
    assert not destination.exists()
    assert not output.exists()
    assert not other_sidecar.exists()
    assert source.read_bytes() == before


def test_snapshot_refuses_existing_destination_and_sidecars(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    source = private / "source.db"
    _database(source)
    destination = private / "copy.db"
    destination.touch(mode=0o600)
    with pytest.raises(ValueError, match="already exist"):
        snapshot(source, destination, private / "manifest.json")

    destination.unlink()
    sidecar = Path(f"{destination}-wal")
    sidecar.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar"):
        snapshot(source, destination, private / "manifest.json")
    assert sidecar.read_text(encoding="utf-8") == "preserve"


def test_baseline_guard_uses_synthetic_git_results_not_live_repository(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace
    from scripts import pension_baseline as driver

    checkout = tmp_path / "synthetic-checkout"
    checkout.mkdir()
    calls = []
    def fake_git_output(command, **kwargs):
        calls.append(command)
        if command[1] == "rev-parse":
            return BASELINE
        if "--ignored" in command:
            return "backend/app/services/__pycache__/salary.cpython-314.pyc\n"
        return ""
    monkeypatch.setattr(driver.subprocess, "check_output", fake_git_output)
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    verified = driver.verify_baseline(checkout, BASELINE)
    assert verified["head"] == BASELINE
    assert calls

    monkeypatch.setattr(driver.subprocess, "check_output", lambda command, **kwargs: "not-the-pinned-ref" if command[1] == "rev-parse" else "")
    with pytest.raises(ValueError, match="HEAD must equal"):
        driver.verify_baseline(checkout, BASELINE)
    monkeypatch.setattr(driver.subprocess, "check_output", fake_git_output)
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match="application/migration files differ"):
        driver.verify_baseline(checkout, BASELINE)


def test_baseline_verifier_rejects_untracked_salary_package_shadow(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace
    from scripts import pension_baseline as driver

    checkout = tmp_path / "shadow-checkout"
    backend = checkout / "backend"
    services = backend / "app/services"
    shadow_package = services / "salary"
    shadow_package.mkdir(parents=True)
    (services / "salary.py").write_text("def calculate_salary(*args): return 'tracked'\n", encoding="utf-8")
    (shadow_package / "__init__.py").write_text("def calculate_salary(*args): return 'shadow'\n", encoding="utf-8")
    commands = []
    def fake_git_output(command, **kwargs):
        commands.append(command)
        if command[1] == "rev-parse":
            return BASELINE
        if "--ignored" in command:
            return "backend/app/services/__pycache__/salary.cpython-314.pyc\n"
        if "--others" in command:
            return "backend/app/services/salary/__init__.py\n"
        return ""
    monkeypatch.setattr(driver.subprocess, "check_output", fake_git_output)
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))

    with pytest.raises(ValueError, match="untracked importable application/migration source"):
        driver.verify_baseline(checkout, BASELINE)
    assert (services / "salary.py").is_file()
    assert (shadow_package / "__init__.py").is_file()
    assert any("--ignored" in command for command in commands)
    assert any("--others" in command and "--exclude-standard" in command for command in commands)


def test_verified_import_worker_uses_clean_checkout_and_rejects_cached_shadow(tmp_path: Path) -> None:
    import sys
    from scripts.pension_baseline import run_import_probe

    producer_backend = tmp_path / "producer" / "backend"
    verified_backend = tmp_path / "verified" / "backend"
    private = _private_dir(tmp_path)
    producer_app = producer_backend / "app"
    verified_app = verified_backend / "app"
    producer_app.mkdir(parents=True)
    verified_app.mkdir(parents=True)
    (producer_app / "__init__.py").write_text("PRODUCER = True\n", encoding="utf-8")
    (producer_app / "fixture.py").write_text("ORIGIN = 'producer'\n", encoding="utf-8")
    (verified_app / "__init__.py").write_text("VERIFIED = True\n", encoding="utf-8")
    (verified_app / "fixture.py").write_text("ORIGIN = 'verified'\n", encoding="utf-8")

    origins = run_import_probe(Path(__file__).resolve().parents[1] / "scripts/pension_baseline.py",
                               verified_backend, ("app.fixture",),
                               env={**os.environ, "PYTHONPATH": str(producer_backend)}, cwd=producer_backend)
    assert Path(origins["module_origins"]["app.fixture"]).is_relative_to(verified_backend.resolve())
    assert not list(verified_backend.rglob("*.pyc"))

    (producer_backend / "sitecustomize.py").write_text(
        "import sys; sys.path.insert(0, __import__('os').environ['PYTHONPATH']); import app\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="rejected module binding"):
        run_import_probe(Path(__file__).resolve().parents[1] / "scripts/pension_baseline.py",
                         verified_backend, ("app.fixture",),
                         env={**os.environ, "PYTHONPATH": str(producer_backend)}, cwd=producer_backend)


def test_alembic_config_uses_absolute_verified_checkout_from_unrelated_cwd(tmp_path: Path, monkeypatch) -> None:
    from alembic.script import ScriptDirectory
    from scripts.pension_baseline import make_alembic_config

    checkout = tmp_path / "pinned-checkout"
    backend = checkout / "backend"
    (backend / "alembic/versions").mkdir(parents=True)
    (backend / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8")
    unrelated = tmp_path / "elsewhere"
    unrelated.mkdir()
    db_path = _private_dir(tmp_path) / "explicit.db"
    monkeypatch.chdir(unrelated)

    config = make_alembic_config(checkout, db_path)
    scripts = ScriptDirectory.from_config(config)

    assert Path(config.get_main_option("script_location")).resolve() == (backend / "alembic").resolve()
    assert Path(scripts.dir).resolve() == (backend / "alembic").resolve()
    assert config.attributes["db_path"] == str(db_path.resolve())


def test_migration_orchestration_passes_explicit_paths_without_live_git_guard(tmp_path: Path, monkeypatch) -> None:
    from argparse import Namespace
    from scripts import pension_baseline as driver

    private = _private_dir(tmp_path)
    source = private / "source.db"
    copy = private / "copy.db"
    with _connect(source) as db:
        db.execute("create table alembic_version (version_num text not null)")
        db.execute("insert into alembic_version values ('018remove_forecasting')")
    checkout = tmp_path / "isolated-checkout"
    checkout.mkdir()
    monkeypatch.setattr(driver, "verify_baseline", lambda path, ref: {"checkout": str(checkout), "baseline_ref": ref, "head": ref})
    calls = {}
    def fake_worker(path, db_path, working_directory=None):
        calls.update(checkout=path, db_path=db_path, cwd=working_directory)
        return {"exit_code": 0, "script_location": str((checkout / "backend/alembic").resolve()),
                "module_origins": {"app.services.salary": str(checkout / "backend/app/services/salary.py")},
                "argv": ["synthetic-worker"], "cwd": str(working_directory)}
    monkeypatch.setattr(driver, "_run_migration_worker", fake_worker)
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    args = Namespace(checkout=checkout, baseline_ref=BASELINE, source=source, copy=copy,
                     snapshot_manifest=private / "snapshot.json", migration_log=private / "migration.log",
                     provenance=private / "provenance.json", working_directory=unrelated)

    result = driver.migrate_copy(args)

    assert result["exit_code"] == 0
    assert calls["db_path"] == copy
    assert calls["cwd"] == unrelated
    assert result["alembic_config_db_path"] == str(copy.resolve())
    assert result["migration_worker"]["script_location"] == str((checkout / "backend/alembic").resolve())


def test_driver_refuses_existing_copy_without_touching_synthetic_paths(tmp_path: Path, monkeypatch) -> None:
    from argparse import Namespace
    from scripts import pension_baseline as driver

    private = _private_dir(tmp_path)
    source = private / "synthetic-source.db"
    copy = private / "pre-existing-copy.db"
    manifest = private / "snapshot.json"
    log = private / "migration.log"
    provenance = private / "provenance.json"
    checkout = tmp_path / "isolated-checkout"
    checkout.mkdir()
    monkeypatch.setattr(driver, "verify_baseline", lambda path, ref: {"checkout": str(checkout), "baseline_ref": ref, "head": ref})
    _database(source)
    copy.write_text("preserve", encoding="utf-8")
    source_before = source.read_bytes()
    with pytest.raises(ValueError, match="already exist"):
        driver.migrate_copy(Namespace(checkout=checkout, baseline_ref=BASELINE, source=source,
                                      copy=copy, snapshot_manifest=manifest, migration_log=log,
                                      provenance=provenance))
    assert source.read_bytes() == source_before
    assert copy.read_text(encoding="utf-8") == "preserve"
    assert not manifest.exists()


def test_private_json_failure_preserves_replacement_file(tmp_path: Path, monkeypatch) -> None:
    from scripts import pension_baseline as driver

    private = _private_dir(tmp_path)
    output = private / "manifest.json"
    moved = private / "reserved-inode.json"

    def replace_then_fail(*_args, **_kwargs):
        output.rename(moved)
        output.write_text("replacement belongs to another writer", encoding="utf-8")
        raise OSError("injected serialization failure")

    monkeypatch.setattr(driver.json, "dump", replace_then_fail)
    with pytest.raises(OSError, match="serialization"):
        driver.write_private_json(output, {"synthetic": True})
    assert output.read_text(encoding="utf-8") == "replacement belongs to another writer"
    assert moved.exists()
    moved.unlink()


def test_asset_boundaries_include_adjacent_months_year_transitions_and_future(tmp_path: Path) -> None:
    from scripts.pension_baseline import _asset_boundaries

    private = _private_dir(tmp_path)
    db_path = private / "boundaries.db"
    with _connect(db_path) as db:
        db.execute("create table salary_config(user_id text, valid_from text)")
        db.execute("insert into salary_config values ('u','2025-04-01')")
        db.execute("create table transfers(user_id text, billing_month text)")
        db.execute("insert into transfers values ('u','2025-09-01')")
        db.execute("create table transactions(user_id text, billing_month text)")
        db.execute("insert into transactions values ('u','2026-03-01')")
        db.execute("create table user_settings(user_id text, key text, value text)")
        db.execute("insert into user_settings values ('u','tracking_start_date','2025-01-01')")
        db.execute("create table assets(user_id text, year int, asset_type text)")
        db.execute("insert into assets values ('u',2025,'pension')")
    with _connect(db_path) as db:
        cutoffs, future = _asset_boundaries(db, "u")
    assert {"2025-03-01", "2025-04-01", "2025-05-01", "2025-08-01", "2025-09-01", "2025-10-01"} <= set(cutoffs)
    assert {"2025-01-01", "2025-12-01", "2026-01-01", "2026-12-01"} <= set(cutoffs)
    assert future == "2027-03-01"
    assert future in cutoffs


def test_protected_manifest_hashes_full_rows_and_owner_attribution(tmp_path: Path) -> None:
    from scripts.pension_baseline import protected_manifest

    private = _private_dir(tmp_path)
    db_path = private / "protected.db"
    with _connect(db_path) as db:
        db.execute("create table users(id text primary key, name text)")
        db.execute("insert into users values ('synthetic-user', 'Example')")
        db.execute("create table accounts(id text primary key, user_id text, opening_balance numeric)")
        db.execute("insert into accounts values ('synthetic-account', 'synthetic-user', 100)")
    original = protected_manifest(db_path)
    assert original["users"]["rows"][json.dumps(["synthetic-user"], separators=(",", ":"))]["owner"] == "synthetic-user"
    with _connect(db_path) as db:
        db.execute("update accounts set opening_balance=101")
    changed = protected_manifest(db_path)
    assert original["accounts"]["table_sha256"] != changed["accounts"]["table_sha256"]


def test_a_to_b_ledger_reports_equal_count_updates_and_table_changes(tmp_path: Path) -> None:
    from scripts.pension_baseline import migration_effects

    private = _private_dir(tmp_path)
    a_path, b_path = private / "A.db", private / "B.db"
    with _connect(a_path) as a:
        a.execute("create table payment_methods(id text primary key, user_id text, linked_bank_id text)")
        a.execute("insert into payment_methods values ('pm', 'u', null)")
        a.execute("create table user_settings(user_id text, key text, value text, primary key(user_id,key))")
        a.execute("insert into user_settings values ('u','old','1')")
        a.execute("create table forecasts(id text primary key)")
        a.execute("insert into forecasts values ('f')")
    with _connect(b_path) as b:
        b.execute("create table payment_methods(id text primary key, user_id text, linked_bank_id text)")
        b.execute("insert into payment_methods values ('pm', 'u', 'bank')")
        b.execute("create table user_settings(user_id text, key text, value text, primary key(user_id,key))")
        b.execute("insert into user_settings values ('u','new','2')")
        b.execute("create table accounts(id text primary key, user_id text, opening_balance numeric)")
        b.execute("insert into accounts values ('a','u',42)")
    ledger = migration_effects(a_path, b_path)
    pm = ledger["common_tables"]["payment_methods"]
    assert pm["changed_rows"] == 1
    assert pm["changed_columns_by_row_count"]["linked_bank_id"] == 1
    assert pm["changed_column_migration"]["linked_bank_id"] == "016backfill_legacy_card_links"
    settings = ledger["common_tables"]["user_settings"]
    assert settings["added_rows"] == settings["deleted_rows"] == 1
    assert "accounts" in ledger["added_tables"]
    assert "forecasts" in ledger["dropped_tables"]
