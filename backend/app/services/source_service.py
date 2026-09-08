from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database.session import Database
from app.repositories.source_json_repository import SourceJsonRepository, SourceNotFound
from app.schemas.source import (
    ACTIVE_STATUSES,
    CalibrationStartRequest,
    CheckoutRequest,
    LocationInfo,
    ReturnRequest,
    Source,
    SourceCreate,
    SourcePatch,
)
from app.services.activity_service import ActivityService
from app.services.audit_service import AuditService
from app.services.transaction_service import TransactionService


TRANSITIONS = {
    "in_stock": {"checked_out", "calibrating"},
    "checked_out": {"in_stock", "calibrating"},
    "calibrating": {"checked_out", "in_stock"},
    "inactive": set(),
}


class SourceService:
    def __init__(self, repository: SourceJsonRepository, database: Database, activity: ActivityService):
        self.repository = repository
        self.database = database
        self.activity = activity
        self.transactions = TransactionService(database)
        self.audit = AuditService(database)

    def list_sources(self, *, status: str | None = None, isotope: str | None = None, location: str | None = None, search: str | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
        sources = self.repository.list_sources()
        search_value = (search or "").casefold()
        result = []
        for source in sources:
            if not include_inactive and source.status == "inactive":
                continue
            if status and source.status != status:
                continue
            if isotope and source.isotope != isotope:
                continue
            if location and location.casefold() not in source.location.as_text().casefold():
                continue
            if search_value and not any(search_value in str(value).casefold() for value in (source.source_id, source.display_name, source.isotope, source.serial_number)):
                continue
            item = source.model_dump(mode="json")
            try:
                item["current_activity"] = self.activity.calculate_activity(source, datetime.now(timezone.utc))
            except ValueError as exc:
                item["current_activity_error"] = str(exc)
            result.append(item)
        return result

    def get_source(self, source_id: str) -> Source:
        return self.repository.get_source(source_id)

    def create(self, payload: SourceCreate, user: dict | None, ip_address: str | None = None) -> Source:
        now = _now()
        source_id = payload.source_id or self.suggest_source_id(payload.isotope)
        source = Source(
            source_id=source_id,
            display_name=payload.display_name,
            isotope=payload.isotope,
            source_type=payload.source_type,
            serial_number=payload.serial_number,
            activity=payload.activity,
            status="in_stock",
            location=payload.location,
            current_holder=None,
            status_since=now,
            manufacturer=payload.manufacturer,
            certificate_number=payload.certificate_number,
            description=payload.description,
            notes=payload.notes,
            created_at=now,
            updated_at=now,
        )
        created = self.repository.create_source(source)
        with self.database.transaction() as connection:
            self.transactions.record(source_id=created.source_id, action="create", from_status=None, to_status="in_stock", operator=_username(user), location_after=created.location.model_dump(), connection=connection)
            self.audit.record(user_id=_user_id(user), username=_username(user), action="source_create", entity_type="source", entity_id=created.source_id, new_data=created.model_dump(mode="json"), ip_address=ip_address, connection=connection)
        return created

    def update(self, source_id: str, payload: SourcePatch, user: dict | None, ip_address: str | None = None) -> Source:
        changes = payload.model_dump(exclude_none=True, mode="json")
        if not changes:
            return self.get_source(source_id)
        old, new = self.repository.update_source(source_id, changes)
        with self.database.transaction() as connection:
            self.transactions.record(source_id=source_id, action="update", from_status=old.status, to_status=new.status, operator=_username(user), location_before=old.location.model_dump(), location_after=new.location.model_dump(), connection=connection)
            self.audit.record(user_id=_user_id(user), username=_username(user), action="source_update", entity_type="source", entity_id=source_id, old_data=old.model_dump(mode="json"), new_data=new.model_dump(mode="json"), ip_address=ip_address, connection=connection)
        return new

    def deactivate(self, source_id: str, user: dict | None, ip_address: str | None = None) -> Source:
        old = self.get_source(source_id)
        if old.status == "inactive":
            return old
        updated = self._change_status(source_id, "inactive", user=user, action="deactivate", comment="source deactivated", ip_address=ip_address, allow_from_any=True)
        return updated

    def reactivate(self, source_id: str, user: dict | None, ip_address: str | None = None) -> Source:
        old = self.get_source(source_id)
        if old.status != "inactive":
            raise ValueError("only inactive sources can be reactivated")
        return self._change_status(source_id, "in_stock", user=user, action="reactivate", comment="source reactivated", ip_address=ip_address, allow_from_any=True)

    def checkout(self, source_id: str, request: CheckoutRequest, user: dict | None, ip_address: str | None = None) -> Source:
        old = self.get_source(source_id)
        if old.status != "in_stock":
            raise ValueError(f"source must be in_stock, currently {old.status}")
        return self._change_status(source_id, "checked_out", user=user, action="checkout", holder=request.holder, purpose=request.purpose, comment=request.comment, ip_address=ip_address, expected_holder=request.holder)

    def return_source(self, source_id: str, request: ReturnRequest, user: dict | None, ip_address: str | None = None) -> Source:
        old = self.get_source(source_id)
        if old.status != "checked_out":
            raise ValueError(f"source must be checked_out, currently {old.status}")
        return self._change_status(source_id, "in_stock", user=user, action="return", comment=request.comment, location_after=request.location, ip_address=ip_address, clear_holder=True)

    def start_calibration(self, source_id: str, request: CalibrationStartRequest, user: dict | None, ip_address: str | None = None) -> tuple[Source, int]:
        old = self.get_source(source_id)
        if old.status not in {"in_stock", "checked_out"}:
            raise ValueError(f"source must be in_stock or checked_out, currently {old.status}")
        source = self._change_status(source_id, "calibrating", user=user, action="calibration_start", operator=request.operator, purpose=request.purpose, comment=request.comment, ip_address=ip_address)
        from app.services.calibration_service import CalibrationService
        record = CalibrationService(self.database, self.repository, self.activity).create(
            {
                "source_id": source_id,
                "source_label_raw": source.display_name,
                "isotope": source.isotope,
                "calibration_system": request.calibration_system,
                "start_time": _now().isoformat(),
                "run_number": request.run_number,
                "position_label": request.position_label,
                "operator": request.operator,
                "purpose": request.purpose,
                "comment": request.comment,
            },
            user=user,
            ip_address=ip_address,
        )
        return source, int(record["id"])

    def end_calibration(self, source_id: str, user: dict | None, ip_address: str | None = None, comment: str = "") -> Source:
        old = self.get_source(source_id)
        if old.status != "calibrating":
            raise ValueError(f"source must be calibrating, currently {old.status}")
        destination = "checked_out" if old.current_holder else "in_stock"
        source = self._change_status(source_id, destination, user=user, action="calibration_end", comment=comment, ip_address=ip_address, clear_holder=destination == "in_stock")
        finished_at = _now().isoformat()
        with self.database.transaction() as connection:
            row = connection.execute("SELECT id, end_time FROM calibration_records WHERE source_id = ? AND end_time IS NULL AND is_deleted = 0 ORDER BY id DESC LIMIT 1", (source_id,)).fetchone()
            if row is not None:
                connection.execute("UPDATE calibration_records SET end_time = ?, updated_at = ? WHERE id = ?", (finished_at, finished_at, row["id"]))
                self.audit.record(user_id=_user_id(user), username=_username(user), action="calibration_finish", entity_type="calibration", entity_id=str(row["id"]), old_data={"end_time": row["end_time"]}, new_data={"end_time": finished_at}, ip_address=ip_address, connection=connection)
        return source

    def _change_status(self, source_id: str, to_status: str, *, user: dict | None, action: str, holder: str | None = None, purpose: str | None = None, operator: str | None = None, comment: str = "", location_after: LocationInfo | None = None, clear_holder: bool = False, expected_holder: str | None = None, ip_address: str | None = None, allow_from_any: bool = False) -> Source:
        old = self.get_source(source_id)
        if not allow_from_any and to_status not in TRANSITIONS.get(old.status, set()):
            raise ValueError(f"invalid status transition {old.status} -> {to_status}")
        changes: dict[str, Any] = {"status": to_status, "status_since": _now().isoformat()}
        if expected_holder is not None:
            changes["current_holder"] = expected_holder
        if clear_holder:
            changes["current_holder"] = None
        if location_after is not None:
            changes["location"] = location_after.model_dump(mode="json")
        _, new = self.repository.update_source(source_id, changes)
        with self.database.transaction() as connection:
            self.transactions.record(source_id=source_id, action=action, from_status=old.status, to_status=to_status, operator=operator or _username(user), holder=holder or old.current_holder, purpose=purpose, location_before=old.location.model_dump(), location_after=new.location.model_dump(), comment=comment, connection=connection)
            self.audit.record(user_id=_user_id(user), username=_username(user), action=f"source_{action}", entity_type="source", entity_id=source_id, old_data=old.model_dump(mode="json"), new_data=new.model_dump(mode="json"), ip_address=ip_address, connection=connection)
        return new

    def suggest_source_id(self, isotope: str) -> str:
        letters = "".join(character for character in isotope.upper() if character.isalnum())
        if not letters:
            letters = "SOURCE"
        existing = {source.source_id for source in self.repository.list_sources()}
        number = 1
        while f"JUNO-CAL-{letters}-{number:03d}" in existing:
            number += 1
        return f"JUNO-CAL-{letters}-{number:03d}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_id(user: dict | None) -> int | None:
    return int(user["id"]) if user and user.get("id") is not None else None


def _username(user: dict | None) -> str | None:
    return str(user["username"]) if user and user.get("username") else None
