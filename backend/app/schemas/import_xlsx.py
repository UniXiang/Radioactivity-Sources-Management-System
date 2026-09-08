from __future__ import annotations

from pydantic import BaseModel, Field


class ImportMapping(BaseModel):
    calibration_date: str | None = None
    source_label_raw: str | None = None
    isotope: str | None = None
    calibration_system: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    run_number: str | None = None
    position_label: str | None = None
    x: str | None = None
    y: str | None = None
    z: str | None = None
    operator: str | None = None
    purpose: str | None = None
    comment: str | None = None


class ImportConfirmRequest(BaseModel):
    upload_token: str = Field(min_length=1)
    sheet_name: str = Field(min_length=1)
    mapping: ImportMapping
    duplicate_policy: str = "skip"

