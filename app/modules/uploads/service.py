import logging
import os
import uuid
from typing import Protocol

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def validate_image(content_type: str, size: int) -> None:
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
    if size > MAX_BYTES:
        raise HTTPException(
            status_code=400, detail="La imagen supera el límite de 5 MB"
        )


class ImageStore(Protocol):
    def save(self, file_bytes: bytes, content_type: str) -> dict: ...


class CloudinaryImageStore:
    def __init__(self) -> None:
        if not settings.cloudinary_cloud_name:
            raise HTTPException(
                status_code=503, detail="Almacenamiento de imágenes no configurado"
            )
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )

    def save(self, file_bytes: bytes, content_type: str) -> dict:
        try:
            result = cloudinary.uploader.upload(
                file_bytes,
                folder="lacabrona/menu",
                resource_type="image",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("cloudinary upload failed: %s", exc)
            raise HTTPException(
                status_code=502, detail="Error al subir la imagen"
            ) from exc
        return {"url": result["secure_url"], "ref": result["public_id"]}


class LocalImageStore:
    def __init__(self, media_dir: str, base_url: str) -> None:
        self.media_dir = media_dir
        self.base_url = base_url.rstrip("/")
        os.makedirs(os.path.join(self.media_dir, "menu"), exist_ok=True)

    def save(self, file_bytes: bytes, content_type: str) -> dict:
        ext = _EXTENSIONS[content_type]
        name = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(self.media_dir, "menu", name)
        with open(path, "wb") as fh:
            fh.write(file_bytes)
        return {
            "url": f"{self.base_url}/media/menu/{name}",
            "ref": f"menu/{name}",
        }


def get_image_store() -> ImageStore:
    if settings.environment == "prod":
        return CloudinaryImageStore()
    return LocalImageStore(settings.media_dir, settings.media_base_url)
