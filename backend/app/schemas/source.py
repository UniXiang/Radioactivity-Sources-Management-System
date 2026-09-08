from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceStatus = Literal["in_stock", "checked_out", "calibrating", "inactive"]
ActivityUnit = Literal["Bq", "n/s"]
ACTIVE_STATUSES = {"in_stock", "checked_out", "calibrating"}


class ActivityInfo(BaseModel):
    reference_value: float = Field(gt=0)
    reference_unit: ActivityUnit = "Bq"
    reference_date: datetime
    uncertainty_fraction: float | None = Field(default=None, ge=0)


class LocationInfo(BaseModel):
    building: str = ""
    room: str = ""
    cabinet: str = ""
    position: str = ""

    def as_text(self) -> str:
        return " / ".join(x for x in (self.building, self.room, self.cabinet, self.position) if x)


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    isotope: str = Field(min_length=1)
    source_type: str = "sealed"
    serial_number: str = ""
    activity: ActivityInfo
    status: SourceStatus
    location: LocationInfo = Field(default_factory=LocationInfo)
    current_holder: str | None = None
    status_since: datetime
    manufacturer: str = ""
    certificate_number: str = ""
    description: str = ""
    notes: str = ""
    created_at: datetime
    updated_at: datetime

    @field_validator("source_id")
    @classmethod
    def source_id_is_stable_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source_id cannot be empty")
        return value


class SourceCreate(BaseModel):
    source_id: str | None = None
    display_name: str
    isotope: str
    source_type: str = "sealed"
    serial_number: str = ""
    activity: ActivityInfo
    location: LocationInfo = Field(default_factory=LocationInfo)
    manufacturer: str = ""
    certificate_number: str = ""
    description: str = ""
    notes: str = ""


class SourcePatch(BaseModel):
    display_name: str | None = None
    isotope: str | None = None
    source_type: str | None = None
    serial_number: str | None = None
    activity: ActivityInfo | None = None
    location: LocationInfo | None = None
    manufacturer: str | None = None
    certificate_number: str | None = None
    description: str | None = None
    notes: str | None = None


class CheckoutRequest(BaseModel):
    holder: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_return_at: datetime | None = None
    comment: str = ""


class ReturnRequest(BaseModel):
    location: LocationInfo = Field(default_factory=LocationInfo)
    comment: str = ""


class CalibrationStartRequest(BaseModel):
    calibration_system: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    run_number: str | None = None
    position_label: str | None = None
    comment: str = ""


class ActivityResponse(BaseModel):
    source_id: str
    isotope: str
    reference_activity: dict[str, Any]
    query_time: datetime
    activity: dict[str, Any]
    remaining_fraction: float
    warning: str | None = None
