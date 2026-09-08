from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class Settings:
    root: Path
    host: str
    port: int
    timezone: str
    sources_file: Path
    database_file: Path
    isotopes_file: Path
    backup_directory: Path
    backup_retention_days: int
    imports_directory: Path
    logs_directory: Path
    session_expire_hours: int
    allow_backward_activity: bool
    session_cookie_secure: bool

    @classmethod
    def from_file(cls, filename: str | Path | None = None) -> "Settings":
        config_path = Path(filename or os.getenv("JCSMS_CONFIG", PROJECT_ROOT / "config/config.yaml"))
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        raw: dict[str, Any] = {}
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        server = raw.get("server", {})
        data = raw.get("data", {})
        backup = raw.get("backup", {})
        security = raw.get("security", {})
        activity = raw.get("activity", {})
        root = PROJECT_ROOT
        return cls(
            root=root,
            host=str(server.get("host", "0.0.0.0")),
            port=int(server.get("port", 8080)),
            timezone=str(raw.get("timezone", "Asia/Shanghai")),
            sources_file=_resolve(root, str(data.get("sources_file", "data/sources.json"))),
            database_file=_resolve(root, str(data.get("database_file", "data/database/juno_sources.db"))),
            isotopes_file=_resolve(root, str(data.get("isotopes_file", "config/isotopes.json"))),
            backup_directory=_resolve(root, str(backup.get("directory", "data/backups"))),
            backup_retention_days=int(backup.get("retention_days", 30)),
            imports_directory=_resolve(root, str(data.get("imports_directory", "data/imports"))),
            logs_directory=_resolve(root, str(raw.get("logs_directory", "logs"))),
            session_expire_hours=int(security.get("session_expire_hours", 12)),
            allow_backward_activity=bool(activity.get("allow_backward_evaluation", True)),
            session_cookie_secure=bool(security.get("session_cookie_secure", False)),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.sources_file.parent,
            self.database_file.parent,
            self.backup_directory / "sources",
            self.backup_directory / "database",
            self.imports_directory,
            self.logs_directory,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings.from_file()
