import os

STORAGE_DIR = os.environ.get(
    "STORAGE_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


class FilesystemBackend:
    def save(self, zoo: str, entity_type: str, filename: str, file_obj) -> str:
        dir_path = os.path.join(STORAGE_DIR, zoo, entity_type)
        os.makedirs(dir_path, exist_ok=True)
        full_path = os.path.join(dir_path, filename)
        file_obj.save(full_path)
        return os.path.join(zoo, entity_type, filename)

    def delete(self, storage_path: str) -> None:
        full_path = os.path.join(STORAGE_DIR, storage_path)
        if os.path.isfile(full_path):
            os.remove(full_path)

    def url(self, storage_path: str) -> str:
        return f"/api/v1/files/{storage_path}"

    def full_path(self, storage_path: str) -> str:
        return os.path.join(STORAGE_DIR, storage_path)


storage = FilesystemBackend()
