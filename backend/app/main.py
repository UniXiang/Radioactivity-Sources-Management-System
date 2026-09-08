from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.api.routes import router
from app.config import Settings, settings as default_settings
from app.database.session import Database
from app.repositories.source_json_repository import SourceJsonRepository, SourceRepositoryError, SourceNotFound
from app.services.activity_service import ActivityCalculationError, ActivityService
from app.services.auth_service import AuthService
from app.services.calibration_service import CalibrationService
from app.services.import_service import ImportService
from app.services.source_service import SourceService


@dataclass
class AppServices:
    settings: Settings
    database: Database
    sources: SourceJsonRepository
    activity: ActivityService
    source_service: SourceService
    calibrations: CalibrationService
    imports: ImportService
    auth: AuthService
    audit: object


def _configure_logging(directory: Path) -> None:
    # The application never logs request bodies or authentication secrets.
    root_logger = logging.getLogger()
    app_log = str((directory / "app.log").resolve())
    error_log = str((directory / "error.log").resolve())
    existing = {getattr(handler, "_jcsms_log_file", None) for handler in root_logger.handlers}
    if app_log not in existing:
        root_logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        app_handler = logging.FileHandler(directory / "app.log", encoding="utf-8")
        app_handler.setFormatter(formatter)
        app_handler._jcsms_log_file = app_log
        root_logger.addHandler(app_handler)
    if error_log not in existing:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        error_handler = logging.FileHandler(directory / "error.log", encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        error_handler._jcsms_log_file = error_log
        root_logger.addHandler(error_handler)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    selected = app_settings or default_settings
    selected.ensure_directories()
    _configure_logging(selected.logs_directory)
    database = Database(selected.database_file)
    database.initialize()
    sources = SourceJsonRepository(selected.sources_file, selected.backup_directory / "sources", selected.backup_retention_days)
    activity = ActivityService(selected.isotopes_file, selected.allow_backward_activity)
    source_service = SourceService(sources, database, activity)
    calibrations = CalibrationService(database, sources, activity)
    imports = ImportService(database, sources, activity, selected.imports_directory)
    auth = AuthService(database, selected.session_expire_hours)
    from app.services.audit_service import AuditService
    service_bundle = AppServices(selected, database, sources, activity, source_service, calibrations, imports, auth, AuditService(database))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.info("JCSMS startup")
        yield
        logging.info("JCSMS shutdown")

    app = FastAPI(title="JUNO Calibration Source Management System", version="1.0.0", lifespan=lifespan)
    app.state.services = service_bundle
    # FastAPI 0.141's lazy ``include_router`` wrapper is not compatible with
    # the minimal ASGI runtime used by some on-site installations. The router
    # already carries the /api/v1 prefix, so registering its concrete routes
    # keeps dispatch deterministic across supported FastAPI versions.
    app.router.routes.extend(router.routes)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "jcsms", "version": "1.0.0"}

    frontend_dist = selected.root / "frontend" / "dist"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "API endpoint not found"}})
        if not frontend_dist.exists():
            return JSONResponse(status_code=404, content={"error": {"code": "FRONTEND_NOT_BUILT", "message": "Frontend assets are not built"}})
        root = frontend_dist.resolve()
        candidate = (root / full_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            candidate = root / "index.html"
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return Response(content=candidate.read_bytes(), media_type=media_type)

    @app.exception_handler(SourceNotFound)
    async def source_not_found(_: Request, exc: SourceNotFound):
        return JSONResponse(status_code=404, content={"error": {"code": "SOURCE_NOT_FOUND", "message": str(exc)}})

    async def business_error(_: Request, exc: Exception):
        return JSONResponse(status_code=400, content={"error": {"code": "BUSINESS_ERROR", "message": str(exc)}})

    async def internal_error(_: Request, exc: Exception):
        logging.getLogger(__name__).exception("Unhandled application error", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        if "code" not in detail:
            detail = {"code": "HTTP_ERROR", "message": detail.get("message", str(detail))}
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    app.add_exception_handler(SourceRepositoryError, business_error)
    app.add_exception_handler(ActivityCalculationError, business_error)
    app.add_exception_handler(ValueError, business_error)
    app.add_exception_handler(Exception, internal_error)

    return app


app = create_app()
