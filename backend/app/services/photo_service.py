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
EXT_BY_CONTENT_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_DIMENSION = 1600
# The cap sits above the largest sensor a phone carries today (~64 MP) and below Pillow's
# own thresholds, which start warning at ~89 MP and refuse outright past ~179 MP. In the
# band between them a declared canvas is still paid for in RAM at decode time, so it is
# refused here as input rather than allocated.
MAX_TOTAL_PIXELS = 80_000_000


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

    ext = EXT_BY_CONTENT_TYPE[content_type]
    fmt = PIL_FORMAT_BY_EXT[ext]

    try:
        # A header alone declares the canvas, so the refusal has to come before any pixels
        # are allocated: a few kilobytes of upload must not cost hundreds of megabytes of RAM.
        image = Image.open(io.BytesIO(file_bytes))
        if image.width * image.height > MAX_TOTAL_PIXELS:
            raise ValidationError("Image dimensions are too large.")
        image.verify()  # detect truncated/corrupt files
        image = Image.open(io.BytesIO(file_bytes))
        if image.format == "JPEG":
            # Ask the decoder for a smaller raster before the pixels exist. A 64-megapixel
            # phone photo is ordinary input; downscaling during the decode keeps the worker
            # from allocating the whole canvas just to shrink it to 1600 px.
            image.draft("RGB", (MAX_DIMENSION, MAX_DIMENSION))
        # A JPEG canvas cannot carry alpha, and a picker that labels a transparent PNG as
        # JPEG is a normal upload rather than bad input, so the target format decides.
        if image.mode not in ("RGB", "RGBA") or (fmt == "JPEG" and image.mode != "RGB"):
            image = image.convert("RGB")
        if max(image.size) > MAX_DIMENSION:
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format=fmt)
    except ValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        # Pillow's own bomb guard fires while a header is being read, so the cheap size
        # check above never gets a turn, and a verified header can still hide a body that
        # fails to decode. Either one escaped as a 500 before this block existed.
        raise ValidationError("File is not a valid image.")

    filename = _safe_filename(uuid.uuid4().hex, ext)
    payload = buffer.getvalue()

    os.makedirs(settings.upload_dir, exist_ok=True)
    dest = os.path.join(settings.upload_dir, filename)
    with open(dest, "wb") as fh:
        fh.write(payload)

    logger.info("Stored upload %s (%d bytes)", filename, len(payload))
    return f"/uploads/{filename}"
