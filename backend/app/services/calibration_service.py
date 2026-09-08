from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from app.database.session import Database
from app.repositories.source_json_repository import SourceJsonRepository
from app.schemas.calibration import CalibrationCreate
from app.services.activity_service import ActivityService
from app.services.audit_service import AuditService, now_iso


class CalibrationService:
    def __init__(self, database: Database, sources: SourceJsonRepository, activity: ActivityService):
        self.database = database
        self.sources = sources
        self.activity = activity
        self.audit = AuditService(database)

    def list(self, *, source_id: str | None = None, isotope: str | None = None, system: str | None = None, run_number: str | None = None, operator: str | None = None, date_from: date | None = None, date_to: date | None = None, search: str | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
        conditions = ["1=1"]
        values: list[Any] = []
        if not include_deleted:
            conditions.append("is_deleted = 0")
        for field, value in (("source_id", source_id), ("isotope", isotope), ("calibration_system", system), ("run_number", run_number), ("operator", operator)):
            if value:
                conditions.append(f"{field} LIKE ?")
                values.append(f"%{value}%")
        if date_from:
            conditions.append("calibration_date >= ?")
            values.append(date_from.isoformat())
        if date_to:
            conditions.append("calibration_date <= ?")
            values.append(date_to.isoformat())
        if search:
            conditions.append("(source_label_raw LIKE ? OR run_number LIKE ? OR operator LIKE ? OR comment LIKE ?)")
            values.extend([f"%{search}%"] * 4)
        rows = self.database.fetch_all(f"SELECT * FROM calibration_records WHERE {' AND '.join(conditions)} ORDER BY COALESCE(start_time, calibration_date) DESC, id DESC", tuple(values))
        return [_row(row) for row in rows]

    def get(self, record_id: int) -> dict[str, Any]:
        row = self.database.fetch_one("SELECT * FROM calibration_records WHERE id = ?", (record_id,))
        if row is None or row["is_deleted"]:
            raise ValueError(f"Calibration {record_id} not found")
        return _row(row)

    def create(self, payload: dict[str, Any] | CalibrationCreate, user: dict | None, ip_address: str | None = None, *, connection=None, import_batch_id: int | None = None, original_sheet: str | None = None, original_row: int | None = None, raw_data: dict | None = None) -> dict[str, Any]:
        data = payload.model_dump(mode="json", exclude_none=True) if isinstance(payload, CalibrationCreate) else dict(payload)
        source = None
        if data.get("source_id"):
            source = self.sources.get_source(data["source_id"])
            data.setdefault("isotope", source.isotope)
        if data.get("start_time") and not data.get("calibration_date"):
            data["calibration_date"] = _parse_datetime(data["start_time"]).date().isoformat()
        elif isinstance(data.get("calibration_date"), date):
            data["calibration_date"] = data["calibration_date"].isoformat()
        for field in ("start_time", "end_time"):
            if isinstance(data.get(field), datetime):
                data[field] = _aware(data[field]).isoformat()
        activity_value = None
        activity_time = data.get("start_time") or data.get("calibration_date")
        if source is not None and source.activity.reference_unit == "Bq" and activity_time:
            activity_value = self.activity.calculate_activity(source, _parse_datetime(activity_time))["reference_activity"]["value"] * self.activity.calculate_remaining_fraction(source, _parse_datetime(activity_time))[0]
        now = now_iso()
        columns = ["source_id", "source_label_raw", "isotope", "calibration_system", "calibration_date", "start_time", "end_time", "run_number", "position_label", "x", "y", "z", "operator", "purpose", "comment", "activity_at_calibration_bq", "import_batch_id", "original_sheet", "original_row", "raw_data_json", "is_deleted", "created_at", "updated_at"]
        values = [data.get(column) for column in columns[:15]] + [activity_value, import_batch_id, original_sheet, original_row, json.dumps(raw_data, ensure_ascii=False, default=str) if raw_data is not None else None, 0, now, now]
        query = f"INSERT INTO calibration_records ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        if connection is not None:
            cursor = connection.execute(query, tuple(values))
            record_id = int(cursor.lastrowid)
            self.audit.record(user_id=_id(user), username=_name(user), action="calibration_create", entity_type="calibration", entity_id=str(record_id), new_data=data, ip_address=ip_address, connection=connection)
            row = connection.execute("SELECT * FROM calibration_records WHERE id = ?", (record_id,)).fetchone()
            return _row(row)
        else:
            with self.database.transaction() as tx:
                cursor = tx.execute(query, tuple(values))
                record_id = int(cursor.lastrowid)
                self.audit.record(user_id=_id(user), username=_name(user), action="calibration_create", entity_type="calibration", entity_id=str(record_id), new_data=data, ip_address=ip_address, connection=tx)
        return self.get(record_id)

    def update(self, record_id: int, payload: CalibrationCreate, user: dict | None, ip_address: str | None = None) -> dict[str, Any]:
        old = self.get(record_id)
        changes = payload.model_dump(mode="json", exclude_none=True)
        if not changes:
            return old
        if changes.get("source_id"):
            source = self.sources.get_source(changes["source_id"])
            changes.setdefault("isotope", source.isotope)
        changes["updated_at"] = now_iso()
        assignments = ", ".join(f"{field} = ?" for field in changes)
        with self.database.transaction() as connection:
            connection.execute(f"UPDATE calibration_records SET {assignments} WHERE id = ? AND is_deleted = 0", tuple(changes.values()) + (record_id,))
            self.audit.record(user_id=_id(user), username=_name(user), action="calibration_update", entity_type="calibration", entity_id=str(record_id), old_data=old, new_data=changes, ip_address=ip_address, connection=connection)
        return self.get(record_id)

    def soft_delete(self, record_id: int, reason: str, user: dict | None, ip_address: str | None = None) -> None:
        old = self.get(record_id)
        with self.database.transaction() as connection:
            connection.execute("UPDATE calibration_records SET is_deleted = 1, deleted_at = ?, deleted_by = ?, delete_reason = ?, updated_at = ? WHERE id = ?", (now_iso(), _id(user), reason, now_iso(), record_id))
            self.audit.record(user_id=_id(user), username=_name(user), action="calibration_delete", entity_type="calibration", entity_id=str(record_id), old_data=old, new_data={"delete_reason": reason}, ip_address=ip_address, connection=connection)


def _row(row) -> dict[str, Any]:
    item = dict(row)
    item["is_deleted"] = bool(item["is_deleted"])
    if item.get("raw_data_json"):
        try:
            item["raw_data"] = json.loads(item["raw_data_json"])
        except json.JSONDecodeError:
            item["raw_data"] = item["raw_data_json"]
    else:
        item["raw_data"] = None
    return item


def _parse_datetime(value: str | datetime | date) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _id(user: dict | None) -> int | None:
    return int(user["id"]) if user else None


def _name(user: dict | None) -> str | None:
    return user.get("username") if user else None
