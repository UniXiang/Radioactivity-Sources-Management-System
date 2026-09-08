from __future__ import annotations

import json
from typing import Any

from app.database.session import Database
from app.services.audit_service import now_iso


class TransactionService:
    def __init__(self, database: Database):
        self.database = database

    def record(
        self,
        *,
        source_id: str,
        action: str,
        from_status: str | None,
        to_status: str | None,
        operator: str | None = None,
        holder: str | None = None,
        purpose: str | None = None,
        location_before: Any = None,
        location_after: Any = None,
        comment: str | None = None,
        connection=None,
    ) -> None:
        params = (
            source_id,
            action,
            from_status,
            to_status,
            operator,
            holder,
            purpose,
            _text(location_before),
            _text(location_after),
            comment,
            now_iso(),
        )
        query = """INSERT INTO source_transactions
            (source_id, action, from_status, to_status, operator, holder, purpose,
             location_before, location_after, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        if connection is not None:
            connection.execute(query, params)
        else:
            with self.database.transaction() as tx:
                tx.execute(query, params)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)

