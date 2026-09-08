#!/usr/bin/env python3
"""Import the current source ledger in source.md into sources.json.

The ledger is a tab-separated Markdown text export.  This script deliberately
keeps the original row and all original columns in each Source record so the
import remains auditable and can be repeated safely.
"""

from __future__ import annotations

import copy
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings
from app.database.session import Database
from app.repositories.source_json_repository import SourceJsonRepository
from app.schemas.source import ActivityInfo, LocationInfo, Source
from app.services.activity_service import ActivityService
from app.services.audit_service import AuditService, now_iso
from app.services.transaction_service import TransactionService


LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
HEADERS = [
    "序号", "备案文号", "内部编号", "核素", "生产单位/来源", "型号",
    "出厂活度（贝可）", "状态", "工作（储存）场所", "用途", "记录人",
    "记录日期", "审核人", "审核日期", "备注",
]


def clean(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text in {"", "\\", "\\\\"} else text


def normalize_isotope(value: str) -> str:
    text = clean(value).replace(" ", "")
    aliases = {
        "Cs137": "Cs-137", "Co60": "Co-60", "Zn65": "Zn-65",
        "Mn54": "Mn-54", "Ge68": "Ge-68", "K40": "K-40",
        "Am241": "Am-241", "Ra226": "Ra-226",
        "AmC": "AmC（中子源）", "AmC(中子源)": "AmC（中子源）",
        "AmBe": "AmBe（中子源）", "AmBe(中子源)": "AmBe（中子源）",
    }
    return aliases.get(text, text)


def parse_date(value: str) -> datetime:
    text = clean(value).replace("/", ".").replace("-", ".")
    match = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
    if not match:
        raise ValueError(f"无法解析台账日期: {value}")
    year, month, day = (int(part) for part in match.groups())
    return datetime(year, month, day, tzinfo=LOCAL_ZONE)


def parse_measurement(value: str) -> tuple[float, str]:
    text = clean(value).replace(",", "")
    match = re.match(r"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)", text)
    if not match:
        raise ValueError(f"无法解析台账活度: {value}")
    number = float(match.group(1))
    unit = "n/s" if "中子/秒" in text else "Bq"
    return number, unit


def parse_rows(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = []
    parent: dict[str, object] | None = None
    for line_number, line in enumerate(lines, start=1):
        columns = [clean(value) for value in line.split("\t")]
        if line_number <= 2 or not any(columns):
            continue
        if columns[0].isdigit() and len(columns) >= len(HEADERS):
            raw = dict(zip(HEADERS, columns[: len(HEADERS)]))
            parent = raw
        elif parent is not None and columns and normalize_isotope(columns[0]) in {
            "Co-60", "Zn-65"
        }:
            # The first ledger entry uses continuation rows with the isotope
            # in column 1 and the activity in column 4.  Inherit the common
            # administrative fields from the parent row.
            raw = copy.deepcopy(parent)
            raw["核素"] = columns[0]
            raw["出厂活度（贝可）"] = columns[3] if len(columns) > 3 else ""
            raw["序号"] = f"{parent.get('序号')}.{len(records) + 1}"
        else:
            continue
        raw["_source_md_row"] = line_number
        records.append(raw)
    return records


def source_from_record(record: dict[str, object], sequence: int) -> Source:
    isotope = normalize_isotope(str(record["核素"]))
    value, unit = parse_measurement(str(record["出厂活度（贝可）"]))
    reference_date = parse_date(str(record["记录日期"]))
    now = datetime.now(timezone.utc)
    ledger_row = int(record["_source_md_row"])
    record_number = str(record.get("序号", ""))
    display_isotope = isotope.replace("（中子源）", "")
    display_name = f"{display_isotope}-{sequence:02d}"
    ledger_status = str(record.get("状态", ""))
    note_lines = [
        f"来源：source.md，第 {ledger_row} 行",
        f"台账状态：{ledger_status or '未填写'}",
        f"用途：{clean(record.get('用途')) or '未填写'}",
        f"记录人：{clean(record.get('记录人')) or '未填写'}；审核人：{clean(record.get('审核人')) or '未填写'}",
        f"审核日期：{clean(record.get('审核日期')) or '未填写'}",
        f"台账备注：{clean(record.get('备注')) or '未填写'}",
    ]
    return Source(
        source_id=f"JUNO-CAL-{re.sub(r'[^A-Za-z0-9]+', '', display_isotope).upper()}-{sequence:03d}",
        display_name=display_name,
        isotope=isotope,
        source_type="neutron" if unit == "n/s" else "sealed",
        serial_number=clean(record.get("内部编号")),
        activity=ActivityInfo(reference_value=value, reference_unit=unit, reference_date=reference_date),
        status="in_stock",
        location=LocationInfo(building=clean(record.get("工作（储存）场所"))),
        current_holder=None,
        status_since=now,
        manufacturer=clean(record.get("生产单位/来源")),
        certificate_number=clean(record.get("备案文号")),
        description="；".join(part for part in (clean(record.get("型号")), clean(record.get("用途"))) if part),
        notes="\n".join(note_lines),
        created_at=now,
        updated_at=now,
        ledger={
            "source_file": "source.md",
            "row": ledger_row,
            "record_number": record_number,
            "status": ledger_status,
            "record_date": reference_date.isoformat(),
            "raw_columns": {key: value for key, value in record.items() if not key.startswith("_")},
        },
    )


def canonical(value: str) -> str:
    text = str(value).replace("（中子源）", "").replace("(中子源)", "")
    return "".join(character.lower() for character in text if character.isalnum())


def link_unique_calibrations(database: Database, repository: SourceJsonRepository, activity: ActivityService) -> int:
    sources = repository.list_sources()
    by_label: dict[str, list[Source]] = defaultdict(list)
    for source in sources:
        by_label[canonical(source.isotope)].append(source)
    linked = 0
    with database.transaction() as connection:
        rows = connection.execute("SELECT * FROM calibration_records WHERE is_deleted = 0 AND source_id IS NULL").fetchall()
        for row in rows:
            label = clean(row["source_label_raw"])
            if not label:
                continue
            candidates = by_label.get(canonical(normalize_isotope(label)), [])
            if len(candidates) != 1:
                continue
            source = candidates[0]
            calibration_time = row["start_time"] or row["calibration_date"]
            activity_value = None
            if source.activity.reference_unit == "Bq" and calibration_time:
                result = activity.calculate_activity(source, _parse_datetime(calibration_time))
                activity_value = result["activity"]["value"] * {"Bq": 1, "kBq": 1_000, "MBq": 1_000_000}[result["activity"]["unit"]]
            connection.execute(
                "UPDATE calibration_records SET source_id = ?, isotope = ?, activity_at_calibration_bq = ?, updated_at = ? WHERE id = ?",
                (source.source_id, source.isotope, activity_value, now_iso(), row["id"]),
            )
            linked += 1
    return linked


def _parse_datetime(value: str) -> datetime:
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> int:
    ledger_path = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.root / "source.md"
    if not ledger_path.exists():
        print(f"找不到台账文件: {ledger_path}", file=sys.stderr)
        return 2
    settings.ensure_directories()
    database = Database(settings.database_file)
    database.initialize()
    repository = SourceJsonRepository(settings.sources_file, settings.backup_directory / "sources", settings.backup_retention_days)
    activity = ActivityService(settings.isotopes_file, settings.allow_backward_activity)
    audit = AuditService(database)
    transactions = TransactionService(database)
    user_row = database.fetch_one("SELECT * FROM users WHERE username = ?", ("juno",))
    user = dict(user_row) if user_row else None
    records = parse_rows(ledger_path)
    counters: dict[str, int] = defaultdict(int)
    for record in records:
        counters[normalize_isotope(str(record["核素"]))] += 1
        source = source_from_record(record, counters[normalize_isotope(str(record["核素"]))])
        try:
            created = repository.create_source(source)
        except ValueError as exc:
            if "already exists" in str(exc):
                continue
            raise
        with database.transaction() as connection:
            transactions.record(source_id=created.source_id, action="create", from_status=None, to_status="in_stock", operator="juno", location_after=created.location.model_dump(), comment="Imported from source.md", connection=connection)
            audit.record(user_id=user["id"] if user else None, username="juno" if user else None, action="source_import", entity_type="source", entity_id=created.source_id, new_data=created.model_dump(mode="json"), connection=connection)
    linked = link_unique_calibrations(database, repository, activity)
    print(f"Parsed ledger rows: {len(records)}")
    print(f"Sources in registry: {len(repository.list_sources())}")
    print(f"Unique calibration records linked: {linked}")
    print("Ambiguous source labels remain unlinked so duplicate isotopes are not guessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
