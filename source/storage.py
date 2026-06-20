import os
from pathlib import Path


# Project root is one level above /source.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Media files are stored below the media root.
# Default:
#   <project-root>/media/<zoo>/<entity_type>/<filename>
#
# Can be overridden with:
#   STORAGE_DIR=/absolute/path/to/media
STORAGE_DIR = os.environ.get("STORAGE_DIR", str(PROJECT_ROOT / "media"))


class FilesystemBackend:
    def _safe_relative_path(self, *parts: str) -> str:
        """
        Build a safe relative path below STORAGE_DIR.

        The returned path never starts with a slash and rejects traversal
        segments such as '..'. This keeps media files inside the configured
        media root.
        """
        clean_parts = []

        for part in parts:
            if part is None:
                raise ValueError("Path part must not be None")

            part = str(part).strip().replace("\\", "/")

            if not part or part.startswith("/") or ".." in part.split("/"):
                raise ValueError("Invalid path part")

            clean_parts.extend(p for p in part.split("/") if p)

        return os.path.join(*clean_parts)

    def _full_path(self, relative_path: str) -> str:
        storage_root = os.path.realpath(STORAGE_DIR)
        full_path = os.path.realpath(os.path.join(storage_root, relative_path))

        if os.path.commonpath([full_path, storage_root]) != storage_root:
            raise ValueError("Invalid storage path")

        return full_path

    def save(self, zoo: str, entity_type: str, filename: str, file_obj) -> str:
        relative_path = self._safe_relative_path(zoo, entity_type, filename)
        full_path = self._full_path(relative_path)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        file_obj.save(full_path)

        # Store relative path in DB, e.g.:
        #   zoo_test1/species/<filename>.jpg
        # This is resolved against STORAGE_DIR by full_path().
        return relative_path

    def delete(self, storage_path: str) -> None:
        full_path = self._full_path(storage_path)
        if os.path.isfile(full_path):
            os.remove(full_path)

    def url(self, storage_path: str) -> str:
        return f"/api/v1/files/{storage_path}"

    def full_path(self, storage_path: str) -> str:
        return self._full_path(storage_path)


storage = FilesystemBackend()
