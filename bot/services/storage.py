import asyncio
import logging
import uuid
from pathlib import PurePosixPath

from supabase import Client, create_client

from config.settings import Settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.supabase_storage_bucket
        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_key,
        )

    async def upload_photo(self, data: bytes, extension: str = "jpg") -> str:
        return await asyncio.to_thread(self._upload_sync, data, extension)

    def _upload_sync(self, data: bytes, extension: str) -> str:
        filename = f"{uuid.uuid4()}.{extension}"
        path = PurePosixPath("visits") / filename

        self._client.storage.from_(self._bucket).upload(
            path=str(path),
            file=data,
            file_options={"content-type": f"image/{extension}"},
        )

        public_url = self._client.storage.from_(self._bucket).get_public_url(
            str(path)
        )
        logger.info("Uploaded photo to %s", path)
        return public_url
