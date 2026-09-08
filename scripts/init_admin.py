#!/usr/bin/env python3
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings
from app.database.session import Database
from app.services.auth_service import AuthService


def main() -> int:
    settings.ensure_directories()
    database = Database(settings.database_file)
    database.initialize()
    username = input("Admin username: ").strip()
    if not username:
        print("Username cannot be empty", file=sys.stderr)
        return 2
    password = getpass.getpass("Admin password (minimum 8 characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if password != confirmation or len(password) < 8:
        print("Passwords must match and be at least 8 characters", file=sys.stderr)
        return 2
    try:
        user = AuthService(database).create_user(username, password, "admin")
    except Exception as exc:
        print(f"Unable to create admin: {exc}", file=sys.stderr)
        return 1
    print(f"Created admin user {user['username']} (id={user['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
