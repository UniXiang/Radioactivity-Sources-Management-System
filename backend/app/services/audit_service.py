from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database.session import Database, json_text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditService:
    def __init__(self, database: Database):
        self.database = database

    def record(
        self,
        *,
        user_id: int | None,
        username: str | None,
        action: str,
        entity_type: str,
        entity_id: str,
        old_data: Any = None,
        new_data: Any = None,
        ip_address: str | None = None,
        connection=None,
    ) -> None:
        params = (
            user_id,
            username,
            action,
            entity_type,
            entity_id,
            json_text(old_data),
            json_text(new_data),
            ip_address,
            now_iso(),
        )
        if connection is not None:
            connection.execute(
                """INSERT INTO audit_logs
                (user_id, username, action, entity_type, entity_id, old_data_json, new_data_json, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                params,
            )
            return
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO audit_logs
                (user_id, username, action, entity_type, entity_id, old_data_json, new_data_json, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                params,
            )

