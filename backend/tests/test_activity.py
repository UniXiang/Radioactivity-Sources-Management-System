from datetime import datetime, timedelta, timezone

from app.schemas.source import ActivityInfo, LocationInfo, Source
from app.services.activity_service import ActivityService


def source(now):
    return Source(
        source_id="TEST-001", display_name="Test", isotope="Test-1",
        activity=ActivityInfo(reference_value=100_000, reference_date=now),
        status="in_stock", location=LocationInfo(), status_since=now,
        created_at=now, updated_at=now,
    )


def test_activity_reference_and_half_lives(test_settings):
    service = ActivityService(test_settings.isotopes_file)
    reference = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = source(reference)
    assert service.calculate_activity(item, reference)["activity"]["value"] == 100
    assert service.calculate_activity(item, reference + timedelta(days=100))["activity"]["value"] == 50
    assert service.calculate_activity(item, reference + timedelta(days=200))["activity"]["value"] == 25
    assert service.calculate_activity(item, reference)["activity"]["unit"] == "kBq"


def test_backward_activity_has_warning(test_settings):
    service = ActivityService(test_settings.isotopes_file)
    reference = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = service.calculate_activity(source(reference), reference - timedelta(days=1))
    assert result["warning"]

