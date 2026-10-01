from __future__ import annotations

import io
import os
import uuid

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
PIL_FORMAT_BY_EXT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
MAX_DIMENSION = 1600


def _safe_filename(stem: str, ext: str) -> str:
    ext = ext.lower()
    if ext not in PIL_FORMAT_BY_EXT:
        ext = ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


async def process_and_store_upload(file_bytes: bytes, content_type: str | None) -> str:
    """Validate, re-encode and persist an uploaded image. Returns its public path.

    Security:
    * rejects unsupported content types and oversized files;
    * re-encodes through Pillow (strips EXIF/metadata, neutralises polyglots);
    * generates a random filename unrelated to user input (no path traversal).
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Unsupported image type. Use JPEG, PNG or WEBP.")
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise ValidationError(f"Image exceeds {settings.max_upload_size_mb} MB limit.")
    if len(file_bytes) == 0:
        raise ValidationError("Empty file.")

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.verify()  # detect truncated/corrupt files
        image = Image.open(io.BytesIO(file_bytes))
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("File is not a valid image.")

    image = image.convert("RGB") if image.mode not in ("RGB", "RGBA") else image
    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    ext = ".jpg" if content_type == "image/jpeg" else (".png" if content_type == "image/png" else ".webp")
    filename = _safe_filename(uuid.uuid4().hex, ext)
    fmt = PIL_FORMAT_BY_EXT[ext]

    os.makedirs(settings.upload_dir, exist_ok=True)
    dest = os.path.join(settings.upload_dir, filename)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    with open(dest, "wb") as fh:
        fh.write(buffer.getvalue())

    logger.info("Stored upload %s (%d bytes)", filename, len(buffer.getvalue()))
    return f"/uploads/{filename}"
