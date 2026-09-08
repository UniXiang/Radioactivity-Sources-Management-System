from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Callable

from pydantic import ValidationError

from app.schemas.source import Source

try:
    import fcntl
except ImportError:  # pragma: no cover - deployment target is Linux
    fcntl = None


class SourceRepositoryError(RuntimeError):
    pass


class SourceNotFound(SourceRepositoryError):
    pass


class SourceJsonRepository:
    """The only component allowed to read or mutate the current Source Registry."""

    def __init__(self, path: str | Path, backup_dir: str | Path | None = None, retention_days: int = 30):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self.retention_days = retention_days
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with self.lock_path.open("a+") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "updated_at": _now().isoformat(), "sources": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("sources"), list):
                raise ValueError("sources.json must contain an object with a sources list")
            for item in raw["sources"]:
                Source.model_validate(item)
            return raw
        except (OSError, json.JSONDecodeError, ValueError, ValidationError) as exc:
            raise SourceRepositoryError(f"Invalid sources registry: {exc}") from exc

    def read_registry(self) -> dict[str, Any]:
        with self._lock():
            return copy.deepcopy(self._read_unlocked())

    def list_sources(self) -> list[Source]:
        return [Source.model_validate(item) for item in self.read_registry()["sources"]]

    def get_source(self, source_id: str) -> Source:
        for source in self.list_sources():
            if source.source_id == source_id:
                return source
        raise SourceNotFound(f"Source {source_id} not found")

    def _write_unlocked(self, document: dict[str, Any]) -> None:
        for item in document.get("sources", []):
            Source.model_validate(item)
        document["schema_version"] = 1
        document["updated_at"] = _now().isoformat()
        self._backup_existing_unlocked()
        fd, temporary_name = tempfile.mkstemp(prefix="sources.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(document, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_name, self.path)
            directory_fd = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def _backup_existing_unlocked(self) -> None:
        if not self.path.exists():
            return
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S_%f")
        shutil.copy2(self.path, self.backup_dir / f"sources_{stamp}.json")
        cutoff = datetime.now().timestamp() - self.retention_days * 86400
        for backup in self.backup_dir.glob("sources_*.json"):
            if backup.stat().st_mtime < cutoff:
                backup.unlink(missing_ok=True)

    def mutate(self, operation: Callable[[dict[str, Any]], Any]) -> Any:
        with self._lock():
            document = self._read_unlocked()
            result = operation(document)
            self._write_unlocked(document)
            return copy.deepcopy(result)

    def create_source(self, source: Source) -> Source:
        def operation(document: dict[str, Any]) -> dict[str, Any]:
            if any(item.get("source_id") == source.source_id for item in document["sources"]):
                raise ValueError(f"Source {source.source_id} already exists")
            document["sources"].append(source.model_dump(mode="json"))
            return source.model_dump(mode="json")

        return Source.model_validate(self.mutate(operation))

    def update_source(self, source_id: str, changes: dict[str, Any]) -> tuple[Source, Source]:
        def operation(document: dict[str, Any]) -> dict[str, Any]:
            for index, item in enumerate(document["sources"]):
                if item.get("source_id") == source_id:
                    old = Source.model_validate(item)
                    item.update(changes)
                    item["updated_at"] = _now().isoformat()
                    new = Source.model_validate(item)
                    document["sources"][index] = new.model_dump(mode="json")
                    return {"old": old.model_dump(mode="json"), "new": new.model_dump(mode="json")}
            raise SourceNotFound(f"Source {source_id} not found")

        result = self.mutate(operation)
        return Source.model_validate(result["old"]), Source.model_validate(result["new"])


def _now() -> datetime:
    return datetime.now(timezone.utc)

