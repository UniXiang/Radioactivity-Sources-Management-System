from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.source import Source


class ActivityCalculationError(ValueError):
    pass


class ActivityService:
    def __init__(self, isotopes_file: str | Path, allow_backward_evaluation: bool = True):
        self.isotopes_file = Path(isotopes_file)
        self.allow_backward_evaluation = allow_backward_evaluation

    def _isotope(self, isotope: str) -> dict[str, Any]:
        try:
            data = json.loads(self.isotopes_file.read_text(encoding="utf-8"))
            item = data.get("isotopes", {}).get(isotope)
        except (OSError, json.JSONDecodeError) as exc:
            raise ActivityCalculationError(f"Unable to load isotope configuration: {exc}") from exc
        if not item:
            raise ActivityCalculationError(f"No half-life configured for isotope {isotope}")
        if item.get("decay_model", "simple_exponential") != "simple_exponential":
            raise ActivityCalculationError(f"Unsupported decay model for isotope {isotope}")
        return item

    def half_life_seconds(self, isotope: str) -> float:
        item = self._isotope(isotope)
        value = float(item.get("half_life_value", 0))
        unit = item.get("half_life_unit")
        factors = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "year": 365.25 * 86400}
        if value <= 0 or unit not in factors:
            raise ActivityCalculationError(f"Invalid half-life for isotope {isotope}")
        return value * factors[unit]

    def calculate_remaining_fraction(self, source: Source, when: datetime) -> tuple[float, str | None]:
        query_time = _aware(when)
        reference_date = _aware(source.activity.reference_date)
        delta = (query_time - reference_date).total_seconds()
        warning = None
        if delta < 0:
            if not self.allow_backward_evaluation:
                raise ActivityCalculationError("reference date is later than query time")
            warning = "query time precedes reference date; backward mathematical evaluation was used"
        fraction = math.pow(2.0, -delta / self.half_life_seconds(source.isotope))
        return fraction, warning

    def calculate_activity(self, source: Source, when: datetime) -> dict[str, Any]:
        fraction, warning = self.calculate_remaining_fraction(source, when)
        value = source.activity.reference_value * fraction
        return {
            "source_id": source.source_id,
            "isotope": source.isotope,
            "reference_activity": {
                "value": source.activity.reference_value,
                "unit": source.activity.reference_unit,
                "date": _aware(source.activity.reference_date),
            },
            "query_time": _aware(when),
            "activity": display_activity(value, source.activity.reference_unit),
            "remaining_fraction": fraction,
            "warning": warning,
        }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def display_unit(value_bq: float, unit: str = "Bq") -> str:
    if unit != "Bq":
        return unit
    magnitude = abs(value_bq)
    if magnitude >= 1_000_000:
        return "MBq"
    if magnitude >= 1_000:
        return "kBq"
    return "Bq"


def display_activity(value_bq: float, source_unit: str = "Bq") -> dict[str, float | str]:
    unit = display_unit(value_bq, source_unit)
    scale = {"Bq": 1, "kBq": 1_000, "MBq": 1_000_000}.get(unit, 1)
    return {"value": value_bq / scale, "unit": unit}
