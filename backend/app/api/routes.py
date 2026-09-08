from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.dependencies import client_ip, current_user, public_viewer, require_role, services
from app.schemas.auth import LoginRequest, UserCreate, UserPatch
from app.schemas.calibration import CalibrationCreate
from app.schemas.import_xlsx import ImportConfirmRequest
from app.schemas.source import CalibrationStartRequest, CheckoutRequest, ReturnRequest, SourceCreate, SourcePatch


router = APIRouter(prefix="/api/v1")


@router.get("/auth/me")
async def auth_me(user=Depends(public_viewer)):
    return user


@router.post("/auth/login")
async def login(request: Request, payload: LoginRequest, service=Depends(services)):
    user = service.auth.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"})
    token, expires = service.auth.create_session(user["id"])
    service.audit.record(user_id=user["id"], username=user["username"], action="login", entity_type="user", entity_id=str(user["id"]), ip_address=client_ip(request))
    response = Response(content=_json(user), media_type="application/json")
    response.set_cookie("jcsms_session", token, httponly=True, samesite="lax", secure=service.settings.session_cookie_secure, expires=expires)
    return response


@router.post("/auth/logout")
async def logout(request: Request, user=Depends(current_user), service=Depends(services)):
    service.auth.logout(request.cookies.get("jcsms_session"))
    service.audit.record(user_id=user["id"], username=user["username"], action="logout", entity_type="user", entity_id=str(user["id"]), ip_address=client_ip(request))
    response = Response(status_code=204)
    response.delete_cookie("jcsms_session")
    return response


@router.get("/dashboard")
async def dashboard(user=Depends(public_viewer), service=Depends(services)):
    sources = service.sources.list_sources()
    active = [source for source in sources if source.status != "inactive"]
    recent = service.database.fetch_all("SELECT * FROM source_transactions ORDER BY created_at DESC, id DESC LIMIT 20")
    return {
        "counts": {
            "total": len(active),
            "in_stock": sum(source.status == "in_stock" for source in active),
            "checked_out": sum(source.status == "checked_out" for source in active),
            "calibrating": sum(source.status == "calibrating" for source in active),
            "inactive": sum(source.status == "inactive" for source in sources),
        },
        "checked_out": [source.model_dump(mode="json") for source in active if source.status == "checked_out"],
        "calibrating": [source.model_dump(mode="json") for source in active if source.status == "calibrating"],
        "recent_activity": [dict(row) for row in recent],
    }


@router.get("/sources")
async def list_sources(status: str | None = None, isotope: str | None = None, location: str | None = None, search: str | None = None, include_inactive: bool = False, user=Depends(public_viewer), service=Depends(services)):
    if user["role"] not in {"admin", "operator"}:
        include_inactive = False
    return service.source_service.list_sources(status=status, isotope=isotope, location=location, search=search, include_inactive=include_inactive)


@router.get("/sources/export.csv")
async def export_sources(status: str | None = None, isotope: str | None = None, location: str | None = None, search: str | None = None, include_inactive: bool = False, user=Depends(public_viewer), service=Depends(services)):
    if user["role"] not in {"admin", "operator"}:
        include_inactive = False
    rows = service.source_service.list_sources(status=status, isotope=isotope, location=location, search=search, include_inactive=include_inactive)
    flattened = []
    for row in rows:
        flattened.append({
            "source_id": row["source_id"], "display_name": row["display_name"], "isotope": row["isotope"],
            "status": row["status"], "current_activity_value": (row.get("current_activity") or {}).get("activity", {}).get("value"),
            "current_activity_unit": (row.get("current_activity") or {}).get("activity", {}).get("unit"),
            "location": row.get("location"), "current_holder": row.get("current_holder"), "updated_at": row["updated_at"],
        })
    return _csv_response(flattened, "sources.csv")


@router.post("/sources", status_code=201)
async def create_source(request: Request, payload: SourceCreate, user=Depends(require_role("admin")), service=Depends(services)):
    return service.source_service.create(payload, user, client_ip(request)).model_dump(mode="json")


@router.get("/sources/{source_id}")
async def get_source(source_id: str, user=Depends(public_viewer), service=Depends(services)):
    source = service.source_service.get_source(source_id)
    return {
        "source": source.model_dump(mode="json"),
        "current_activity": service.activity.calculate_activity(source, datetime.now().astimezone()),
        "calibrations": service.calibrations.list(source_id=source_id),
        "transactions": [dict(row) for row in service.database.fetch_all("SELECT * FROM source_transactions WHERE source_id = ? ORDER BY created_at DESC, id DESC", (source_id,))],
    }


@router.patch("/sources/{source_id}")
async def update_source(request: Request, source_id: str, payload: SourcePatch, user=Depends(require_role("admin")), service=Depends(services)):
    return service.source_service.update(source_id, payload, user, client_ip(request)).model_dump(mode="json")


@router.post("/sources/{source_id}/deactivate")
async def deactivate_source(request: Request, source_id: str, user=Depends(require_role("admin")), service=Depends(services)):
    return service.source_service.deactivate(source_id, user, client_ip(request)).model_dump(mode="json")


@router.post("/sources/{source_id}/reactivate")
async def reactivate_source(request: Request, source_id: str, user=Depends(require_role("admin")), service=Depends(services)):
    return service.source_service.reactivate(source_id, user, client_ip(request)).model_dump(mode="json")


@router.post("/sources/{source_id}/checkout")
async def checkout_source(request: Request, source_id: str, payload: CheckoutRequest, user=Depends(require_role("operator", "admin")), service=Depends(services)):
    return service.source_service.checkout(source_id, payload, user, client_ip(request)).model_dump(mode="json")


@router.post("/sources/{source_id}/return")
async def return_source(request: Request, source_id: str, payload: ReturnRequest, user=Depends(require_role("operator", "admin")), service=Depends(services)):
    return service.source_service.return_source(source_id, payload, user, client_ip(request)).model_dump(mode="json")


@router.post("/sources/{source_id}/calibration/start")
async def start_calibration(request: Request, source_id: str, payload: CalibrationStartRequest, user=Depends(require_role("operator", "admin")), service=Depends(services)):
    source, calibration_id = service.source_service.start_calibration(source_id, payload, user, client_ip(request))
    return {"source": source.model_dump(mode="json"), "calibration_id": calibration_id}


@router.post("/sources/{source_id}/calibration/end")
async def end_calibration(request: Request, source_id: str, comment: str = "", user=Depends(require_role("operator", "admin")), service=Depends(services)):
    return service.source_service.end_calibration(source_id, user, client_ip(request), comment).model_dump(mode="json")


@router.get("/sources/{source_id}/activity")
async def source_activity(source_id: str, time: datetime | None = None, user=Depends(public_viewer), service=Depends(services)):
    source = service.source_service.get_source(source_id)
    return service.activity.calculate_activity(source, time or datetime.now().astimezone())


@router.get("/calibrations")
async def list_calibrations(source_id: str | None = None, isotope: str | None = None, system: str | None = None, run_number: str | None = None, operator: str | None = None, date_from=None, date_to=None, search: str | None = None, user=Depends(public_viewer), service=Depends(services)):
    return service.calibrations.list(source_id=source_id, isotope=isotope, system=system, run_number=run_number, operator=operator, date_from=_date(date_from), date_to=_date(date_to), search=search)


@router.get("/calibrations/export.csv")
async def export_calibrations(source_id: str | None = None, isotope: str | None = None, system: str | None = None, run_number: str | None = None, operator: str | None = None, date_from=None, date_to=None, search: str | None = None, user=Depends(public_viewer), service=Depends(services)):
    rows = service.calibrations.list(source_id=source_id, isotope=isotope, system=system, run_number=run_number, operator=operator, date_from=_date(date_from), date_to=_date(date_to), search=search)
    return _csv_response(rows, "calibrations.csv")


@router.get("/calibrations/{record_id}")
async def get_calibration(record_id: int, user=Depends(public_viewer), service=Depends(services)):
    return service.calibrations.get(record_id)


@router.post("/calibrations", status_code=201)
async def create_calibration(request: Request, payload: CalibrationCreate, user=Depends(require_role("operator", "admin")), service=Depends(services)):
    return service.calibrations.create(payload, user, client_ip(request))


@router.patch("/calibrations/{record_id}")
async def update_calibration(request: Request, record_id: int, payload: CalibrationCreate, user=Depends(require_role("operator", "admin")), service=Depends(services)):
    return service.calibrations.update(record_id, payload, user, client_ip(request))


@router.post("/calibrations/{record_id}/delete", status_code=204)
async def delete_calibration(request: Request, record_id: int, reason: str = "", user=Depends(require_role("admin")), service=Depends(services)):
    service.calibrations.soft_delete(record_id, reason, user, client_ip(request))
    return Response(status_code=204)


@router.post("/import/xlsx/preview")
async def preview_xlsx(request: Request, user=Depends(require_role("admin")), service=Depends(services)):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, detail={"code": "FILE_REQUIRED", "message": "Upload an XLSX file in field file"})
        filename = getattr(upload, "filename", "upload.xlsx") or "upload.xlsx"
        content = await upload.read()
    else:
        filename = request.headers.get("x-filename", "upload.xlsx")
        content = await request.body()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(400, detail={"code": "INVALID_FILE_TYPE", "message": "Only XLSX files are supported"})
    try:
        return service.imports.save_upload(filename, content)
    except Exception as exc:
        raise HTTPException(400, detail={"code": "XLSX_READ_ERROR", "message": str(exc)}) from exc


@router.post("/import/xlsx/validate")
async def validate_xlsx(payload: dict[str, Any], user=Depends(require_role("admin")), service=Depends(services)):
    from app.schemas.import_xlsx import ImportMapping
    return service.imports.validate(payload["upload_token"], payload["sheet_name"], ImportMapping.model_validate(payload.get("mapping", {})))


@router.post("/import/xlsx/confirm")
async def confirm_xlsx(request: Request, payload: ImportConfirmRequest, user=Depends(require_role("admin")), service=Depends(services)):
    upload_info = service.imports.save_upload  # keep service ownership of files; metadata is supplied by client after preview
    path = service.imports.directory / f"{payload.upload_token}.xlsx"
    if not path.exists():
        raise HTTPException(400, detail={"code": "UPLOAD_NOT_FOUND", "message": "Upload preview has expired or is missing"})
    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    filename = request.headers.get("x-filename", path.name)
    try:
        return service.imports.confirm(upload_token=payload.upload_token, filename=filename, sha256=digest, sheet_name=payload.sheet_name, mapping=payload.mapping, user=user, ip_address=client_ip(request), duplicate_policy=payload.duplicate_policy)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "IMPORT_REJECTED", "message": str(exc)}) from exc


@router.get("/import/batches")
async def import_batches(user=Depends(require_role("admin")), service=Depends(services)):
    return service.imports.list_batches()


@router.get("/audit")
async def audit_logs(limit: int = 200, user=Depends(require_role("admin")), service=Depends(services)):
    rows = service.database.fetch_all("SELECT * FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT ?", (max(1, min(limit, 1000)),))
    return [dict(row) for row in rows]


@router.get("/admin/users")
async def list_users(user=Depends(require_role("admin")), service=Depends(services)):
    return service.auth.list_users()


@router.post("/admin/users", status_code=201)
async def create_user(payload: UserCreate, user=Depends(require_role("admin")), service=Depends(services)):
    return service.auth.create_user(payload.username, payload.password, payload.role)


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: int, payload: UserPatch, user=Depends(require_role("admin")), service=Depends(services)):
    return service.auth.update_user(user_id, **payload.model_dump(exclude_none=True))


def _date(value: str | None):
    if not value:
        return None
    from datetime import date
    return date.fromisoformat(value)


def _csv_response(rows: list[dict[str, Any]], filename: str):
    output = io.StringIO()
    if rows:
        fields = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)
