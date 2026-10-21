"""Replayable, opt-in baseline migration and read-only evidence producer.

Every command requires explicit input/output paths. No path defaults to an
original deployment artifact. See --help for the verify, migrate, and capture
operations; pytest never invokes this script against private data.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.machinery
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .pension_snapshot import _check_private_parent, _reserve_private_file, _unlink_owned, snapshot
except ImportError:  # Executed directly as a script from backend/scripts.
    from pension_snapshot import _check_private_parent, _reserve_private_file, _unlink_owned, snapshot

BASELINE = "0dea247bc8ed465b0d85da60fe6c0a4804ff085e"
PROTECTED_TABLES = (
    "users", "payment_methods", "accounts", "salary_config", "transactions",
    "transfers", "tax_config", "user_settings", "main_bank_history",
    "card_bank_link_history",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_private_json(path: Path, data: Any) -> None:
    path = path.absolute()
    _check_private_parent(path)
    fd = _reserve_private_file(path)
    inode = os.fstat(fd).st_ino
    try:
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
            json.dump(data, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        _unlink_owned(path, inode)
        raise
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _untracked_importable_sources(checkout: Path) -> list[str]:
    pathspec = ["--", "backend/app", "backend/alembic"]
    commands = (
        ["git", "ls-files", "--others", "--exclude-standard", *pathspec],
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", *pathspec],
    )
    candidates: set[str] = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=checkout, text=True)
        candidates.update(line for line in output.splitlines() if line)
    source_suffixes = set(importlib.machinery.SOURCE_SUFFIXES + importlib.machinery.EXTENSION_SUFFIXES)
    result = []
    for relative in candidates:
        path = Path(relative)
        if path.suffix in source_suffixes:
            result.append(relative)
        elif path.suffix == ".pyc" and "__pycache__" not in path.parts:
            # PEP 3147 __pycache__ bytecode is generated/non-importable without
            # its tracked source. Legacy sourceless .pyc files can be imported.
            result.append(relative)
    return sorted(result)


def verify_baseline(checkout: Path, baseline_ref: str) -> dict[str, Any]:
    checkout = checkout.resolve(strict=True)
    if baseline_ref != BASELINE:
        raise ValueError(f"this rehearsal supports only pinned baseline {BASELINE}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    if head != baseline_ref:
        raise ValueError("checkout HEAD must equal the pinned baseline ref")
    if subprocess.run(["git", "diff", "--quiet", baseline_ref, "--", "backend/app", "backend/alembic"], cwd=checkout).returncode:
        raise ValueError("application/migration files differ from the pinned baseline")
    untracked_sources = _untracked_importable_sources(checkout)
    if untracked_sources:
        details = ", ".join(untracked_sources[:5])
        raise ValueError(f"untracked importable application/migration source is not baseline code: {details}")
    return {"baseline_ref": baseline_ref, "checkout": str(checkout), "head": head,
            "untracked_importable_source_count": 0}


def make_alembic_config(checkout: Path, db_path: Path):
    """Build Alembic config with absolute migration and database targets."""
    from alembic.config import Config

    checkout = checkout.resolve(strict=True)
    backend = checkout / "backend"
    ini = backend / "alembic.ini"
    script_location = (backend / "alembic").resolve(strict=True)
    if not ini.is_file() or not script_location.is_dir():
        raise ValueError("verified checkout must contain backend/alembic.ini and backend/alembic")
    if db_path is None:
        raise ValueError("an explicit disposable database path is required")
    config = Config(str(ini))
    config.set_main_option("script_location", str(script_location))
    config.attributes["db_path"] = str(db_path.resolve())
    return config


def _run_migration_worker(checkout: Path, db_path: Path, working_directory: Path | None = None) -> dict[str, Any]:
    script = Path(__file__).resolve()
    argv = [sys.executable, "-B", str(script), "_migration-worker", "--checkout", str(checkout.resolve()),
            "--baseline-ref", BASELINE, "--db-path", str(db_path.resolve())]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    process = subprocess.run(argv, cwd=working_directory, env=env, capture_output=True, text=True)
    if process.returncode:
        return {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
                "argv": argv, "cwd": str(working_directory.resolve()) if working_directory else None}
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
                "argv": argv, "cwd": str(working_directory.resolve()) if working_directory else None}
    result.update({"exit_code": process.returncode, "stderr": process.stderr, "argv": argv,
                   "cwd": str(working_directory.resolve()) if working_directory else None})
    return result


def _migration_worker(checkout: Path, db_path: Path, baseline_ref: str) -> dict[str, Any]:
    verification = verify_baseline(checkout, baseline_ref)
    cached = sorted(name for name in sys.modules if name == "app" or name.startswith("app."))
    if cached:
        raise RuntimeError("application modules were loaded before baseline migration binding")
    backend = (checkout.resolve() / "backend").resolve()
    sys.path.insert(0, str(backend))
    from alembic import command
    from alembic.script import ScriptDirectory

    config = make_alembic_config(checkout, db_path)
    script_directory = ScriptDirectory.from_config(config)
    if Path(script_directory.dir).resolve() != (backend / "alembic").resolve():
        raise RuntimeError("Alembic resolved a script directory outside the verified checkout")
    from contextlib import redirect_stderr, redirect_stdout
    import io
    log = io.StringIO()
    with redirect_stdout(log), redirect_stderr(log):
        command.upgrade(config, "018remove_forecasting")
    origins = app_module_origins(backend)
    return {**verification, "script_location": str(Path(script_directory.dir).resolve()),
            "db_path": str(db_path.resolve()), "target_revision": "018remove_forecasting",
            "module_origins": origins, "migration_output": log.getvalue()}


def migrate_copy(args: argparse.Namespace) -> dict[str, Any]:
    checkout = Path(args.checkout).resolve(strict=True)
    verification = verify_baseline(checkout, args.baseline_ref)
    source, destination = Path(args.source).absolute(), Path(args.copy).absolute()
    manifest_path, log_path, provenance_path = map(Path, (args.snapshot_manifest, args.migration_log, args.provenance))
    _check_private_parent(log_path)
    _check_private_parent(provenance_path)
    snapshot(source, destination, manifest_path)
    log_fd = _reserve_private_file(log_path)
    migration = _run_migration_worker(checkout, destination, getattr(args, "working_directory", None))
    log_text = migration.get("migration_output", "")
    if migration.get("stderr"):
        log_text += migration["stderr"]
    if migration.get("stdout") and not migration.get("migration_output"):
        log_text += migration["stdout"]
    with os.fdopen(log_fd, "w", encoding="utf-8", closefd=False) as log:
        log.write(log_text)
        log.flush()
        os.fsync(log.fileno())
    os.close(log_fd)
    with closing(sqlite3.connect(f"file:{destination}?mode=ro", uri=True)) as db:
        revision = db.execute("select version_num from alembic_version").fetchone()
        integrity = [r[0] for r in db.execute("pragma integrity_check")]
        fk_count = sum(1 for _ in db.execute("pragma foreign_key_check"))
    producer = Path(__file__).resolve()
    record = {
        **verification,
        "operation": "migrate-explicit-copy-to-018remove_forecasting",
        "resolved_source": str(source.resolve()),
        "resolved_copy": str(destination.resolve()),
        "resolved_snapshot_manifest": str(manifest_path.resolve()),
        "resolved_migration_log": str(log_path.resolve()),
        "alembic_config_db_path": str(destination.resolve()),
        "migration_worker": {key: migration.get(key) for key in ("argv", "cwd", "exit_code", "script_location", "module_origins")},
        "args": {"baseline_ref": args.baseline_ref, "target_revision": "018remove_forecasting"},
        "exit_code": migration.get("exit_code", 1),
        "source_sha256": sha256(source),
        "copy_sha256": sha256(destination),
        "producer_sha256": sha256(producer),
        "snapshot_manifest_sha256": sha256(manifest_path),
        "migration_log_sha256": sha256(log_path),
        "result_revision": revision[0] if revision else None,
        "integrity_check": integrity,
        "foreign_key_violation_count": fk_count,
    }
    write_private_json(provenance_path, record)
    if record["exit_code"]:
        raise RuntimeError(f"baseline migration failed; inspect private log {log_path}")
    return record


def _canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    return value


def table_rows(connection: sqlite3.Connection, table: str) -> tuple[list[str], dict[str, tuple[dict[str, Any], str]]]:
    columns = [r[1] for r in connection.execute(f'pragma table_info("{table}")')]
    primary = [r[1] for r in sorted((r for r in connection.execute(f'pragma table_info("{table}")') if r[5]), key=lambda x: x[5])]
    rows: dict[str, tuple[dict[str, Any], str]] = {}
    for row in connection.execute(f'select * from "{table}"'):
        values = {col: _canonical(row[i]) for i, col in enumerate(columns)}
        key = json.dumps([values[k] for k in primary], sort_keys=True, separators=(",", ":")) if primary else str(row[0])
        owner = values.get("user_id")
        if table == "users":
            owner = values.get("id")
        digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()
        rows[key] = ({"owner": owner, "row_sha256": digest}, json.dumps(values, sort_keys=True, separators=(",", ":"), default=str))
    return columns, rows


def protected_manifest(db_path: Path) -> dict[str, Any]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("pragma query_only=on")
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        result: dict[str, Any] = {}
        for table in PROTECTED_TABLES:
            if table not in tables:
                result[table] = {"present": False}
                continue
            columns, rows = table_rows(db, table)
            ordered = sorted((key, meta[0]["row_sha256"]) for key, meta in rows.items())
            table_digest = hashlib.sha256(json.dumps(ordered, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            result[table] = {
                "present": True,
                "columns": columns,
                "column_sha256": hashlib.sha256(json.dumps(columns, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                "row_count": len(rows),
                "table_sha256": table_digest,
                "rows": {key: meta[0] for key, meta in rows.items()},
            }
        return result


def _month(value: str) -> date:
    parsed = date.fromisoformat(value)
    return parsed.replace(day=1)


def _offset(month: date, months: int) -> date:
    index = month.year * 12 + month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _asset_boundaries(db: sqlite3.Connection, user_id: str) -> tuple[list[str], str]:
    months: set[date] = set()
    for (raw,) in db.execute("select valid_from from salary_config where user_id=?", (user_id,)):
        try: months.add(_month(raw))
        except (ValueError, TypeError): pass
    for table in ("transfers", "transactions"):
        if db.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone():
            for (raw,) in db.execute(f"select billing_month from {table} where user_id=?", (user_id,)):
                try: months.add(_month(raw))
                except (ValueError, TypeError): pass
    for (raw,) in db.execute("select value from user_settings where user_id=? and key='tracking_start_date'", (user_id,)):
        try: months.add(_month(raw))
        except (ValueError, TypeError): pass
    for (year,) in db.execute("select year from assets where user_id=? and asset_type='pension'", (user_id,)):
        months.add(date(int(year), 12, 1))
    if not months:
        months.add(date.today().replace(day=1))
    first, last = min(months), max(months)
    for year in range(first.year, last.year + 1):
        months.add(date(year, 1, 1)); months.add(date(year, 12, 1))
    for boundary in tuple(months):
        months.add(_offset(boundary, -1)); months.add(boundary); months.add(_offset(boundary, 1))
    future = _offset(last, 12)
    months.add(future)
    return [m.isoformat() for m in sorted(months)], future.isoformat()


CONTROL_MODULES = (
    "app.config", "app.database", "app.models", "app.models.account", "app.models.salary",
    "app.models.tax", "app.models.user", "app.services.assets", "app.services.salary",
    "app.services.summary", "app.services.tax",
)


def app_module_origins(backend: Path) -> dict[str, str]:
    backend = backend.resolve(strict=True)
    origins: dict[str, str] = {}
    for name, module in sorted(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        origin = getattr(module, "__file__", None)
        if not origin:
            raise RuntimeError(f"baseline module has no verifiable file origin: {name}")
        resolved = Path(origin).resolve(strict=True)
        if not resolved.is_relative_to(backend):
            raise RuntimeError(f"application module loaded outside verified checkout: {name}")
        origins[name] = str(resolved)
    if not origins:
        raise RuntimeError("no application modules were imported from the verified checkout")
    return origins


def bind_baseline_modules(backend: Path, module_names: tuple[str, ...] = CONTROL_MODULES) -> dict[str, str]:
    cached = sorted(name for name in sys.modules if name == "app" or name.startswith("app."))
    if cached:
        raise RuntimeError(f"application modules were cached before fresh baseline import: {cached}")
    backend = backend.resolve(strict=True)
    sys.path.insert(0, str(backend))
    for name in module_names:
        importlib.import_module(name)
    return app_module_origins(backend)


def _controls_from_baseline_modules(db_path: Path) -> dict[str, Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.account import Account
    from app.models.salary import SalaryConfig
    from app.models.tax import TaxConfig
    from app.models.user import User
    from app.services.assets import compute_assets
    from app.services.salary import calculate_salary, SalaryCalculationError
    from app.services.summary import monthly_summary
    from app.services.tax import resolve_tax_config

    uri = db_path.resolve().as_uri() + "?mode=ro"
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    result: dict[str, Any] = {"database_sha256": sha256(db_path), "users": []}
    with Session(engine) as session:
        for user in session.query(User).order_by(User.id).all():
            uid = user.id
            user_report: dict[str, Any] = {"owner_id": uid, "salary": [], "tax_configs": [], "assets": [], "controls": []}
            salary_rows = session.query(SalaryConfig).filter_by(user_id=uid).order_by(SalaryConfig.valid_from).all()
            effective_months = set()
            for cfg in salary_rows:
                effective_months.add(cfg.valid_from)
                tax = resolve_tax_config(session, cfg.valid_from[:7], uid)
                entry = {"salary_config_id": cfg.id, "valid_from": cfg.valid_from,
                         "tax_config_id": tax.id if tax else None, "tax_valid_from": tax.valid_from if tax else None}
                if tax:
                    try: entry["breakdown"] = calculate_salary(cfg, tax).__dict__
                    except SalaryCalculationError as exc: entry["calculation_error"] = str(exc)
                else: entry["calculation_error"] = "no applicable tax config"
                user_report["salary"].append(entry)
            tax_rows = session.query(TaxConfig).filter((TaxConfig.user_id == uid) | (TaxConfig.user_id.is_(None))).order_by(TaxConfig.valid_from).all()
            user_report["tax_configs"] = [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in tax_rows]
            boundary_list, future_cutoff = _asset_boundaries(session.connection().connection, uid)
            accounts = session.query(Account).filter_by(user_id=uid, is_active=True).all()
            for cutoff in boundary_list:
                year = int(cutoff[:4])
                asset_rows = compute_assets(uid, year, session, cutoff)
                by_id = {r.account_id: r.__dict__ for r in asset_rows if r.account_id}
                for account in accounts:
                    user_report["assets"].append({"account_id": account.id, "as_of": cutoff,
                        "future_cutoff": cutoff == future_cutoff,
                        "service_omitted_account": account.id not in by_id,
                        "service_row": by_id.get(account.id)})
            for month in sorted({c[:7] + "-01" for c in boundary_list}):
                year, mon = int(month[:4]), int(month[5:7])
                user_report["controls"].append(monthly_summary(uid, year, mon, session))
            result["users"].append(user_report)
    engine.dispose()
    return result


def _control_worker(checkout: Path, db_path: Path, baseline_ref: str) -> dict[str, Any]:
    verification = verify_baseline(checkout, baseline_ref)
    backend = (checkout.resolve() / "backend").resolve(strict=True)
    origins = bind_baseline_modules(backend)
    controls_payload = _controls_from_baseline_modules(db_path)
    return {"controls": controls_payload, "binding": {
        **verification, "backend_dir": str(backend), "module_origins": origins,
        "module_origin_verified": True, "worker_pid": os.getpid(), "worker_exit_code": 0,
    }}


def run_import_probe(producer_script: Path, backend: Path, module_names: tuple[str, ...],
                     *, env: dict[str, str] | None = None, cwd: Path | None = None) -> dict[str, Any]:
    argv = [sys.executable, "-B", str(producer_script.resolve()), "_probe-import", "--backend", str(backend.resolve())]
    for module in module_names:
        argv.extend(("--module", module))
    process = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(f"fresh import probe rejected module binding (exit {process.returncode})")
    return json.loads(process.stdout)


def controls(db_path: Path, checkout: Path) -> dict[str, Any]:
    checkout = checkout.resolve(strict=True)
    backend = checkout / "backend"
    argv = [sys.executable, "-B", str(Path(__file__).resolve()), "_control-worker", "--checkout", str(checkout),
            "--baseline-ref", BASELINE, "--db-path", str(db_path.resolve())]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    process = subprocess.run(argv, cwd=backend, env=env, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(f"fresh baseline service worker failed (exit {process.returncode})")
    payload = json.loads(process.stdout)
    binding = payload["binding"]
    binding.update({"argv": argv, "worker_exit_code": process.returncode,
                    "stderr_sha256": hashlib.sha256(process.stderr.encode()).hexdigest()})
    return {"controls": payload["controls"], "binding": binding}


def hazards(db_path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("pragma query_only=on")
        dup = db.execute("select count(*) from (select 1 from salary_config group by user_id,valid_from having count(*)>1)").fetchone()[0]
        undated = db.execute("select count(*) from accounts where type='pension' and cast(opening_balance as real)<>0").fetchone()[0] if db.execute("select 1 from sqlite_master where type='table' and name='accounts'").fetchone() else 0
        bad_override = db.execute("select count(*) from assets a left join accounts x on x.id=a.account_id and x.user_id=a.user_id and x.type='pension' where a.asset_type='pension' and a.manual_override is not null and (a.account_id is null or x.id is null)").fetchone()[0] if db.execute("select 1 from sqlite_master where type='table' and name='accounts'").fetchone() else 0
        salaries = db.execute("select user_id,valid_from,ral,employer_contrib_rate,voluntary_contrib_rate from salary_config").fetchall()
        invalid_date = invalid_money = tax_missing = 0
        contributors: set[str] = set()
        for uid, raw, ral, employer, employee in salaries:
            try:
                if _month(raw).isoformat() != raw: invalid_date += 1
            except (ValueError, TypeError): invalid_date += 1
            try:
                if ral is None or float(ral) < 0 or any(rate is None or not 0 <= float(rate) <= 1 for rate in (employer, employee)): invalid_money += 1
                if float(employer or 0) > 0 or float(employee or 0) > 0: contributors.add(uid)
            except (TypeError, ValueError): invalid_money += 1
            if not db.execute("select 1 from tax_config where valid_from<=? and (user_id=? or user_id is null) limit 1", (raw, uid)).fetchone(): tax_missing += 1
        ambiguous = sum(1 for uid in contributors if db.execute("select count(*) from accounts where user_id=? and type='pension'", (uid,)).fetchone()[0] != 1)
        return {"conflicting_salary_effective_dates": dup, "malformed_or_noncanonical_salary_dates": invalid_date,
                "invalid_salary_rates_or_base": invalid_money, "salary_periods_without_applicable_tax_config": tax_missing,
                "nonzero_undated_pension_openings": undated, "ambiguous_or_missing_contribution_destinations": ambiguous,
                "unmatched_or_foreign_owned_nonnul_pension_overrides": bad_override}


def migration_effects(a_path: Path, b_path: Path) -> dict[str, Any]:
    def read(path: Path):
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        db.execute("pragma query_only=on")
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
        return db, tables
    a, at = read(a_path); b, bt = read(b_path)
    try:
        result: dict[str, Any] = {"added_tables": {}, "dropped_tables": {}, "common_tables": {}}
        for table in sorted(bt-at):
            migration = {"card_bank_link_history": "013card_link_history", "accounts": "015account_identities"}.get(table, "013-016 existing baseline")
            cols, rows = table_rows(b, table)
            result["added_tables"][table] = {"columns": cols, "column_sha256": hashlib.sha256(json.dumps(cols, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                "row_count": len(rows), "rows": {key: meta[0] for key, meta in rows.items()}, "migration": migration}
        for table in sorted(at-bt):
            cols, rows = table_rows(a, table)
            result["dropped_tables"][table] = {"columns": cols, "column_sha256": hashlib.sha256(json.dumps(cols, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                "row_count": len(rows), "rows": {key: meta[0] for key, meta in rows.items()},
                "migration": "018remove_forecasting" if table.startswith("forecast") else "existing baseline migration; inspect private row evidence"}
        for table in sorted(at & bt):
            acols = [r[1] for r in a.execute(f'pragma table_info("{table}")')]
            bcols = [r[1] for r in b.execute(f'pragma table_info("{table}")')]
            a_columns, a_rows = table_rows(a, table); b_columns, b_rows = table_rows(b, table)
            added, deleted = set(b_rows)-set(a_rows), set(a_rows)-set(b_rows)
            changed = set(a_rows)&set(b_rows)
            changed_keys = [k for k in changed if a_rows[k][0]["row_sha256"] != b_rows[k][0]["row_sha256"]]
            changed_cols = Counter()
            for key in changed_keys:
                av=json.loads(a_rows[key][1]);bv=json.loads(b_rows[key][1])
                for col in set(av)|set(bv):
                    if av.get(col)!=bv.get(col): changed_cols[col]+=1
            migration_map = {"card_bank_link_history": "013card_link_history", "accounts": "015account_identities",
                             "linked_bank_id": "016backfill_legacy_card_links"}
            added_col_map = {col: migration_map.get(table, "013-016 existing baseline") for col in sorted(set(bcols)-set(acols))}
            deleted_col_map = {col: migration_map.get(table, "013-016 existing baseline") for col in sorted(set(acols)-set(bcols))}
            deleted_migration = "017remove_orphans" if table in {"accounts", "assets", "salary_config"} and deleted else None
            if table == "user_settings" and deleted:
                deleted_migration = "015account_identities (legacy opening-balance conversion)"
            added_row_migration = {
                "accounts": "015account_identities",
                "card_bank_link_history": "013card_link_history + 016backfill_legacy_card_links",
            }.get(table, "013-016 existing baseline; table attribution above")
            result["common_tables"][table] = {
                "added_columns": sorted(set(bcols)-set(acols)), "added_column_migration": added_col_map,
                "dropped_columns": sorted(set(acols)-set(bcols)), "dropped_column_migration": deleted_col_map,
                "added_rows": len(added), "deleted_rows": len(deleted), "changed_rows": len(changed_keys),
                "added_row_manifest": {key: b_rows[key][0] for key in sorted(added)},
                "deleted_row_manifest": {key: a_rows[key][0] for key in sorted(deleted)},
                "changed_row_manifest": {key: {"A": a_rows[key][0], "B": b_rows[key][0]} for key in sorted(changed_keys)},
                "changed_columns_by_row_count": dict(sorted(changed_cols.items())),
                "changed_column_migration": {col: migration_map.get(col, "013-016 existing baseline") for col in sorted(changed_cols)},
                "deleted_row_migration": deleted_migration,
                "added_row_migration": added_row_migration if added else None,
            }
        return result
    finally:
        a.close(); b.close()


def capture(args: argparse.Namespace) -> dict[str, Any]:
    checkout = Path(args.checkout)
    verified = verify_baseline(checkout, args.baseline_ref)
    a_path, b_path = Path(args.a), Path(args.b)
    service_capture = controls(b_path, checkout)
    result = {**verified, "a_path": str(a_path.resolve()), "b_path": str(b_path.resolve()),
              "a_sha256": sha256(a_path), "b_sha256": sha256(b_path),
              "A_to_B_effects": migration_effects(a_path, b_path),
              "B_protected_row_manifest": protected_manifest(b_path),
              "B_controls": service_capture["controls"],
              "control_import_binding": service_capture["binding"],
              "backfill_hazards": hazards(b_path)}
    write_private_json(Path(args.output), result)
    provenance_args = {key: str(value.resolve()) if isinstance(value, Path) else value for key, value in vars(args).items()}
    provenance = {"operation": "read-only-capture-and-A-to-B-ledger", "args": provenance_args,
                  "exit_code": 0, "producer_sha256": sha256(Path(__file__).resolve()),
                  "snapshot_helper_sha256": sha256(Path(__file__).with_name("pension_snapshot.py")),
                  "control_worker_module_origins": result["control_import_binding"]["module_origins"],
                  "control_worker_exit_code": result["control_import_binding"]["worker_exit_code"],
                  "artifact_sha256": sha256(Path(args.output)), "a_sha256": result["a_sha256"], "b_sha256": result["b_sha256"]}
    write_private_json(Path(args.provenance), provenance)
    return {"output": str(Path(args.output).resolve()), "output_sha256": provenance["artifact_sha256"],
            "provenance": str(Path(args.provenance).resolve()), "hazards": result["backfill_hazards"]}


def _internal_main(operation: str) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    if operation == "_control-worker":
        parser.add_argument("--checkout", required=True, type=Path)
        parser.add_argument("--baseline-ref", required=True)
        parser.add_argument("--db-path", required=True, type=Path)
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps(_control_worker(args.checkout, args.db_path, args.baseline_ref), default=str))
            return 0
        except Exception as exc:
            print(f"control worker rejected baseline binding: {type(exc).__name__}", file=sys.stderr)
            return 2
    if operation == "_migration-worker":
        parser.add_argument("--checkout", required=True, type=Path)
        parser.add_argument("--baseline-ref", required=True)
        parser.add_argument("--db-path", required=True, type=Path)
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps(_migration_worker(args.checkout, args.db_path, args.baseline_ref), default=str))
            return 0
        except Exception as exc:
            print(f"migration worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    if operation == "_probe-import":
        parser.add_argument("--backend", required=True, type=Path)
        parser.add_argument("--module", required=True, action="append")
        args = parser.parse_args(sys.argv[2:])
        try:
            print(json.dumps({"module_origins": bind_baseline_modules(args.backend, tuple(args.module))}))
            return 0
        except Exception as exc:
            print(f"import probe rejected module binding: {type(exc).__name__}", file=sys.stderr)
            return 2
    return 2


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].startswith("_"):
        raise SystemExit(_internal_main(sys.argv[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("verify", "migrate", "capture"):
        p = sub.add_parser(name)
        p.add_argument("--checkout", required=True, type=Path)
        p.add_argument("--baseline-ref", required=True)
        if name == "verify":
            p.add_argument("--output", required=True, type=Path)
        elif name == "migrate":
            p.add_argument("--source", required=True, type=Path)
            p.add_argument("--copy", required=True, type=Path)
            p.add_argument("--snapshot-manifest", required=True, type=Path)
            p.add_argument("--migration-log", required=True, type=Path)
            p.add_argument("--provenance", required=True, type=Path)
            p.add_argument("--working-directory", type=Path)
        else:
            p.add_argument("--a", required=True, type=Path)
            p.add_argument("--b", required=True, type=Path)
            p.add_argument("--output", required=True, type=Path)
            p.add_argument("--provenance", required=True, type=Path)
    args = parser.parse_args()
    if args.operation == "verify":
        result = verify_baseline(args.checkout, args.baseline_ref)
        result.update({"operation": "verify-pinned-baseline", "producer_sha256": sha256(Path(__file__).resolve()), "exit_code": 0})
        write_private_json(args.output, result)
    elif args.operation == "migrate":
        result = migrate_copy(args)
    else:
        result = capture(args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
