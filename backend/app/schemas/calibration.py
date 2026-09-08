from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class CalibrationCreate(BaseModel):
    source_id: str | None = None
    source_label_raw: str | None = None
    isotope: str | None = None
    calibration_system: str | None = None
    calibration_date: date | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    run_number: str | None = None
    position_label: str | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    operator: str | None = None
    purpose: str | None = None
    comment: str | None = None


class CalibrationPatch(CalibrationCreate):
    pass

