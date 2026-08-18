from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.core.config.settings import BACKEND_ROOT, settings


class StorageService:
    def __init__(self):
        self.local_root = BACKEND_ROOT / settings.local_upload_dir

    def store(self, *, user_id: str, filename: str, content: bytes, content_type: str) -> str:
        safe_name = self._safe_filename(filename)
        storage_path = f"users/{user_id}/{safe_name}"
        if self._upload_to_supabase(storage_path, content, content_type):
            return f"supabase://{settings.supabase_storage_bucket}/{storage_path}"
        local_path = self.local_root / storage_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        return f"local://{storage_path}"

    def resolve(self, storage_path: str) -> Path:
        if storage_path.startswith("local://"):
            return self.local_root / storage_path.replace("local://", "", 1)
        if storage_path.startswith("supabase://"):
            content = self._download_from_supabase(storage_path)
            cache_path = self.local_root / "_cache" / self._safe_filename(storage_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            return cache_path
        return Path(storage_path)

    def read_bytes(self, storage_path: str) -> bytes:
        return self.resolve(storage_path).read_bytes()

    def _upload_to_supabase(self, path: str, content: bytes, content_type: str) -> bool:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            return False
        url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(url, headers=headers, content=content)
                return response.status_code in {200, 201}
        except httpx.HTTPError:
            return False

    def _download_from_supabase(self, storage_path: str) -> bytes:
        path = storage_path.replace(f"supabase://{settings.supabase_storage_bucket}/", "", 1)
        url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{path}"
        headers = {"Authorization": f"Bearer {settings.supabase_service_role_key}", "apikey": settings.supabase_service_role_key or ""}
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 404:
                raise FileNotFoundError(path)
            response.raise_for_status()
            return response.content

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-")
        return name or "upload.bin"
