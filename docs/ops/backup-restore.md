# Ops Runbook — Backup & Restore

> Last updated: Phase 9 (Reliability). Applies to any environment running a
> real Rentora database — dev SQLite or production PostgreSQL.

## Why this matters

Rentora has **no backup strategy without this runbook**: a crashed disk or a
botched migration on the production box would silently destroy the entire
catalogue, users, bookings and payment records. Backups are cheap; losing
the database is unrecoverable.

---

## 1. Backing up

### Automated (recommended)

Run `scripts/backup_db.py` **daily** from cron (Linux/prod) or Task Scheduler
(Windows):

```bash
# Linux cron — 2:00 AM daily
0 2 * * * cd /path/to/rentora && python3 scripts/backup_db.py --keep 30
```

The script:

- Detects the engine from `backend/.env` (`DB_ENGINE=postgres` → `pg_dump`,
  anything else → SQLite consistent copy via the sqlite backup API).
- Writes to `backend/backups/rentora-<engine>-<timestamp>.<ext>`.
- Prunes to the newest `--keep` (default 14) backups.

> **Production hardening:** back up to a **separate volume / object store**
> (S3, Google Drive, another host), not just the same disk. Off-site backups
> are the whole point — a dead server often means a dead disk.
> Rotate with `--keep 30` and copy the newest file off-site after each run.

### Manual

```bash
# SQLite
python scripts/backup_db.py

# PostgreSQL — direct dump
pg_dump "postgresql://USER:PASS@HOST:5432/rentora" --no-owner -f manual-backup.sql
```

### Media files (room images, avatars, chat uploads)

The database does **not** contain uploaded images — `backend/media/` is a
separate filesystem. Back it up alongside the DB (rsync/tar into the same
object store). In production this should move to S3-compatible storage so it
survives a server wipe.

---

## 2. Restoring

### Restore a SQLite backup

```bash
# Stop the dev server, then:
cp backend/backups/rentora-sqlite-<timestamp>.sqlite3 backend/db.sqlite3
cd backend && venv/Scripts/python manage.py migrate   # apply any migrations made since
```

### Restore a PostgreSQL dump

```bash
# On the target DB host:
psql -h HOST -U USER -d rentora -f rentora-pg-<timestamp>.sql

# Or restore to a fresh empty database:
createdb -h HOST -U USER rentora_restored
psql -h HOST -U USER -d rentora_restored -f rentora-pg-<timestamp>.sql
```

### Restore media

```bash
tar -xzf media-backup.tar.gz -C backend/   # back in place at backend/media/
```

---

## 3. Restore drill (do this quarterly)

1. Spin up a throwaway copy of the stack (docker-compose or a second venv).
2. Restore the newest backup into it.
3. Assert: `Room.objects.count()` matches the source, a booking exists,
   `manage.py check` passes, and the admin login works.
4. Record the result + timestamp in the repo's `docs/ops/` notes.

A backup that has never been restored is a wish, not a backup.

---

## 4. Recovery checklist (incident)

- [ ] Confirm the failure scope (DB only? media too?)
- [ ] Pick the **newest** backup *before* the incident time
- [ ] Restore DB (section 2) — apply migrations if needed
- [ ] Restore media from the same backup date
- [ ] Verify counts + log in + spot-check a listing
- [ ] Restart web/worker processes
- [ ] Post-incident: why did the old backup miss this window? Tighten schedule.
