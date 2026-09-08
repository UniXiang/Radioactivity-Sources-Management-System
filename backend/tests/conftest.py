from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.services.auth_service import AuthService


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    isotopes = tmp_path / "isotopes.json"
    isotopes.write_text(json.dumps({"schema_version": 1, "isotopes": {
        "Test-1": {"half_life_value": 100, "half_life_unit": "day", "decay_model": "simple_exponential"},
        "Ge-68": {"half_life_value": 270.95, "half_life_unit": "day", "decay_model": "simple_exponential"},
    }}), encoding="utf-8")
    return Settings(
        root=tmp_path,
        host="127.0.0.1",
        port=8080,
        timezone="Asia/Shanghai",
        sources_file=tmp_path / "data" / "sources.json",
        database_file=tmp_path / "data" / "database.db",
        isotopes_file=isotopes,
        backup_directory=tmp_path / "backups",
        backup_retention_days=30,
        imports_directory=tmp_path / "imports",
        logs_directory=tmp_path / "logs",
        session_expire_hours=12,
        allow_backward_activity=True,
        session_cookie_secure=False,
    )


@pytest.fixture()
def app(test_settings):
    application = create_app(test_settings)
    application.state.services.auth.create_user("admin", "admin-password", "admin")
    application.state.services.auth.create_user("operator", "operator-password", "operator")
    application.state.services.auth.create_user("viewer", "viewer-password", "viewer")
    return application
