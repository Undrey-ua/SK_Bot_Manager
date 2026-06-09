"""Завантаження фото клієнта з веб-панелі."""

from __future__ import annotations

from fastapi import UploadFile

from bot.services.storage import StorageService

_ALLOWED = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


async def read_cover_upload(cover: UploadFile | None) -> tuple[bytes, str] | None:
    if cover is None or not cover.filename:
        return None
    content_type = (cover.content_type or "").lower()
    if content_type not in _ALLOWED:
        return None
    data = await cover.read()
    if not data:
        return None
    ext = _EXT.get(content_type, "jpg")
    if cover.filename and "." in cover.filename:
        guess = cover.filename.rsplit(".", 1)[-1].lower()
        if guess in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg" if guess == "jpeg" else guess
    return data, ext


async def upload_client_cover(
    storage: StorageService,
    client_id: int,
    cover: UploadFile | None,
) -> str | None:
    parsed = await read_cover_upload(cover)
    if parsed is None:
        return None
    data, ext = parsed
    return await storage.upload_client_cover(client_id, data, ext)
