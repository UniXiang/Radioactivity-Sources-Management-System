#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings


def main() -> int:
    settings.ensure_directories()
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    sources_target = settings.backup_directory / "sources" / f"sources_{stamp}.json"
    database_target = settings.backup_directory / "database" / f"juno_sources_{stamp}.db"
    if settings.sources_file.exists():
        shutil.copy2(settings.sources_file, sources_target)
    if settings.database_file.exists():
        with sqlite3.connect(settings.database_file) as source_db, sqlite3.connect(database_target) as backup_db:
            source_db.backup(backup_db)
    cutoff = datetime.now().timestamp() - settings.backup_retention_days * 86400
    for folder, pattern in ((settings.backup_directory / "sources", "sources_*.json"), (settings.backup_directory / "database", "juno_sources_*.db")):
        for old_backup in folder.glob(pattern):
            if old_backup.stat().st_mtime < cutoff:
                old_backup.unlink(missing_ok=True)
    print(f"Sources backup: {sources_target if settings.sources_file.exists() else 'skipped'}")
    print(f"Database backup: {database_target if settings.database_file.exists() else 'skipped'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
