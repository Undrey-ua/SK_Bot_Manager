import logging
import uuid
from urllib.parse import quote

import httpx

from config.settings import Settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class StorageService:
    """Завантаження в Supabase Storage через REST API (async httpx)."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.supabase_url.rstrip("/")
        self._api_key = settings.supabase_key
        self._bucket = settings.supabase_storage_bucket

    async def _upload_bytes(self, object_path: str, data: bytes, extension: str) -> str:
        encoded_path = quote(object_path, safe="/")
        upload_url = f"{self._base_url}/storage/v1/object/{self._bucket}/{encoded_path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "apikey": self._api_key,
            "Content-Type": f"image/{extension}",
            "x-upsert": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(upload_url, content=data, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            logger.error("Storage HTTP %s: %s", exc.response.status_code, body)
            if exc.response.status_code == 404:
                raise StorageError(
                    f"Bucket «{self._bucket}» не знайдено. Створіть його в Supabase → Storage."
                ) from exc
            if exc.response.status_code in (401, 403):
                raise StorageError(
                    "Невірний SUPABASE_KEY. Потрібен Secret key (sb_secret_...) з Supabase → API Keys."
                ) from exc
            raise StorageError(f"Storage помилка {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.exception("Storage connection error")
            raise StorageError(
                "Не вдалося підключитися до Supabase Storage. Перевірте SUPABASE_URL та мережу."
            ) from exc

        public_url = (
            f"{self._base_url}/storage/v1/object/public/{self._bucket}/{encoded_path}"
        )
        logger.info("Uploaded photo to %s", object_path)
        return public_url

    async def upload_photo(self, data: bytes, extension: str = "jpg") -> str:
        filename = f"{uuid.uuid4()}.{extension}"
        return await self._upload_bytes(f"visits/{filename}", data, extension)

    async def upload_client_cover(
        self, client_id: int, data: bytes, extension: str = "jpg"
    ) -> str:
        ext = extension.lower().lstrip(".") or "jpg"
        if ext == "jpeg":
            ext = "jpg"
        return await self._upload_bytes(f"clients/{client_id}/cover.{ext}", data, ext)
