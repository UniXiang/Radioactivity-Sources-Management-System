#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore JCSMS files while preserving the current files as .before-restore copies.")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    if not args.sources and not args.database:
        parser.error("provide --sources and/or --database")
    settings.ensure_directories()
    if args.sources:
        if not args.sources.exists():
            parser.error(f"missing sources backup: {args.sources}")
        if settings.sources_file.exists():
            shutil.copy2(settings.sources_file, settings.sources_file.with_suffix(".json.before-restore"))
        shutil.copy2(args.sources, settings.sources_file)
        print(f"Restored sources registry from {args.sources}")
    if args.database:
        if not args.database.exists():
            parser.error(f"missing database backup: {args.database}")
        if settings.database_file.exists():
            shutil.copy2(settings.database_file, settings.database_file.with_suffix(".db.before-restore"))
        shutil.copy2(args.database, settings.database_file)
        print(f"Restored database from {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
