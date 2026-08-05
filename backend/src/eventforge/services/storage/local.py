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
        storage_uri = target.resolve().as_uri()
        return target, storage_uri

    def resolve_path(self, storage_uri: str) -> Path:
        """Map a ``file://`` storage URI back to a local path."""
        if storage_uri.startswith("file://"):
            return Path(storage_uri.removeprefix("file://"))
        return Path(storage_uri)

    def exists(self, storage_uri: str) -> bool:
        return self.resolve_path(storage_uri).is_file()


def get_local_storage(settings: Settings | None = None) -> LocalStorage:
    return LocalStorage(settings)
