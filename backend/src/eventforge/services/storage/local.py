"""Persist uploaded project files on local disk."""

import re
import uuid
from pathlib import Path

from eventforge.core.config import Settings, get_settings

_UNSAFE_FILENAME = re.compile(r"[^\w.\-() ]+")


def sanitize_filename(filename: str) -> str:
    """Strip path components and unsafe characters from an upload filename."""
    base = Path(filename).name.strip()
    if not base:
        msg = "Filename must not be empty"
        raise ValueError(msg)
    cleaned = _UNSAFE_FILENAME.sub("_", base)
    return cleaned or "upload.bin"


class LocalStorage:
    """Save and resolve uploaded assets under ``{upload_root}/{project_id}/``."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._root = Path(self._settings.upload_root)

    @property
    def root(self) -> Path:
        return self._root

    def project_dir(self, project_id: uuid.UUID) -> Path:
        return self._root / str(project_id)

    def save_bytes(
        self,
        project_id: uuid.UUID,
        filename: str,
        content: bytes,
    ) -> tuple[Path, str]:
        """Write content to disk and return absolute path + storage URI."""
        safe_name = sanitize_filename(filename)
        project_dir = self.project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        target = project_dir / safe_name
        target.write_bytes(content)
        # Relative URI so host workers and container API share the same upload_root mount.
        storage_uri = f"{project_id}/{safe_name}"
        return target, storage_uri

    def resolve_path(self, storage_uri: str) -> Path:
        """Map a storage URI to a local path under upload_root."""
        if storage_uri.startswith("file://"):
            raw = Path(storage_uri.removeprefix("file://"))
            if raw.is_file():
                return raw
            return self._remap_legacy_container_path(storage_uri) or raw
        candidate = self._root / storage_uri
        if candidate.is_file():
            return candidate
        return self._remap_legacy_container_path(storage_uri) or candidate

    def _remap_legacy_container_path(self, storage_uri: str) -> Path | None:
        """Map Docker API paths (file:///app/data/uploads/...) onto local upload_root."""
        marker = "/data/uploads/"
        if marker not in storage_uri:
            return None
        suffix = storage_uri.split(marker, 1)[1]
        candidate = self._root / suffix
        return candidate if candidate.is_file() else None

    def exists(self, storage_uri: str) -> bool:
        return self.resolve_path(storage_uri).is_file()


def get_local_storage(settings: Settings | None = None) -> LocalStorage:
    return LocalStorage(settings)
