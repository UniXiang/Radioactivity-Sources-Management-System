import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.repositories.source_json_repository import SourceJsonRepository, SourceRepositoryError
from app.schemas.source import ActivityInfo, LocationInfo, Source


def make_source(source_id="TEST-001"):
    now = datetime.now(timezone.utc)
    return Source(source_id=source_id, display_name="Test", isotope="Ge-68", activity=ActivityInfo(reference_value=100, reference_date=now), status="in_stock", location=LocationInfo(), status_since=now, created_at=now, updated_at=now)


def test_create_read_update_and_status(tmp_path):
    path = tmp_path / "sources.json"
    repo = SourceJsonRepository(path, tmp_path / "backups")
    repo.create_source(make_source())
    old, new = repo.update_source("TEST-001", {"status": "checked_out", "current_holder": "Zhang", "status_since": datetime.now(timezone.utc).isoformat()})
    assert old.status == "in_stock"
    assert new.status == "checked_out"
    assert repo.get_source("TEST-001").current_holder == "Zhang"
    assert list((tmp_path / "backups").glob("sources_*.json"))


def test_malformed_json_does_not_get_overwritten(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text('{"sources": [}', encoding="utf-8")
    repo = SourceJsonRepository(path, tmp_path / "backups")
    with pytest.raises(SourceRepositoryError):
        repo.create_source(make_source())
    assert path.read_text(encoding="utf-8") == '{"sources": [}'


def test_concurrent_updates_keep_both_sources(tmp_path):
    path = tmp_path / "sources.json"
    repo = SourceJsonRepository(path, tmp_path / "backups")
    repo.create_source(make_source("TEST-001"))
    repo.create_source(make_source("TEST-002"))

    def update(source_id, holder):
        repo.update_source(source_id, {"current_holder": holder, "status": "checked_out", "status_since": datetime.now(timezone.utc).isoformat()})

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda item: update(*item), [("TEST-001", "A"), ("TEST-002", "B")]))
    current = {source.source_id: source.current_holder for source in repo.list_sources()}
    assert current == {"TEST-001": "A", "TEST-002": "B"}
