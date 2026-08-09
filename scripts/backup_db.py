#!/usr/bin/env python3
"""Rentora database backup script — safe to run from cron / Task Scheduler.

Works with the project's real databases:
- SQLite (dev, default): makes a consistent copy via the sqlite3 backup API
  (safe even while the dev server holds the file open).
- PostgreSQL (prod): shells out to ``pg_dump`` with the DB_* env values.

Usage
-----
    python scripts/backup_db.py [--out DIR]

Default output dir: ``backend/backups/`` (git-ignored), filenames are
``rentora-<db>-<YYYYmmdd-HHMMSS>.<ext>``. Old backups are pruned keeping the
newest ``--keep N`` (default 14).

Examples
--------
    # Windows Task Scheduler / cron, daily at 2am:
    python scripts/backup_db.py
    # Keep 30 days of backups:
    python scripts/backup_db.py --keep 30
"""

import argparse
import datetime as dt
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def _load_env() -> dict:
    """Best-effort read of backend/.env (dotenv not required at runtime)."""
    env = {}
    env_path = BACKEND_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def backup_sqlite(db_path: Path, out_dir: Path) -> Path:
    dest = out_dir / f"rentora-sqlite-{dt.datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dest


def backup_postgres(env: dict, out_dir: Path) -> Path:
    dest = out_dir / f"rentora-pg-{dt.datetime.now():%Y%m%d-%H%M%S}.sql"
    cmd = [
        "pg_dump",
        f"--dbname=postgresql://{env.get('DB_USER', 'postgres')}:{env.get('DB_PASSWORD', '')}@"
        f"{env.get('DB_HOST', 'localhost')}:{env.get('DB_PORT', '5432')}/{env.get('DB_NAME', 'rentora')}",
        "--format=plain",
        "--no-owner",
        f"--file={dest}",
    ]
    subprocess.run(cmd, check=True)
    return dest


def prune(out_dir: Path, keep: int) -> None:
    backups = sorted(out_dir.glob("rentora-*"))
    for old in backups[:-keep] if len(backups) > keep else []:
        old.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BACKEND_DIR / "backups"))
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()

    env = _load_env()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    db_engine = env.get("DB_ENGINE", "sqlite")

    if db_engine == "postgres":
        dest = backup_postgres(env, out_dir)
        kind = "postgres"
    else:
        sqlite_path = BACKEND_DIR / "db.sqlite3"
        if not sqlite_path.exists():
            print(f"ERROR: no database found at {sqlite_path} (and DB_ENGINE != postgres)")
            return 1
        dest = backup_sqlite(sqlite_path, out_dir)
        kind = "sqlite"

    prune(out_dir, args.keep)
    print(f"OK: {kind} backup written to {dest} ({dest.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
