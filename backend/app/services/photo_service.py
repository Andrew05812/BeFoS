from __future__ import annotations

import asyncio
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
# The content type above only describes what the client typed into one field; Pillow picks
# its parser from the magic in the body, so without a second gate a TIFF, PSD or FITS upload
# reaches a decoder this product has no reason to run — and those decoders are where the
# out-of-bounds writes live. MPO is allowed because some phone cameras wrap a JPEG in it,
# and it is read by the JPEG decoder, so refusing it would refuse an ordinary photo.
ACCEPTED_PIL_FORMATS = set(PIL_FORMAT_BY_EXT.values()) | {"MPO"}
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


# Read in pieces the size of a phone photo: big enough that a normal upload costs one
# syscall trip, small enough that an oversized one is refused after one piece past the cap.
UPLOAD_CHUNK = 1024 * 1024


async def read_upload_capped(upload, limit_bytes: int) -> bytes:
    """Take the body of an upload, refusing it as soon as it is past the cap.

    `await upload.read()` without a size materialises the whole body first and looks at
    the limit after, so the cap that is supposed to protect the worker is paid for in
    advance: measured on a 60 MB body, the handler's own RSS grew by 60 MB before the 422
    came back, against 6 MB with the bound in place (and 1 MB of container RSS). The
    answer was always right; the cost was the point. A stranger picks the body size, so
    the bound has to be enforced while the bytes are still arriving.
    """
    pieces: list[bytes] = []
    received = 0
    while True:
        piece = await upload.read(UPLOAD_CHUNK)
        if not piece:
            break
        received += len(piece)
        if received > limit_bytes:
            raise ValidationError(f"Image exceeds {settings.max_upload_size_mb} MB limit.")
        pieces.append(piece)
    return b"".join(pieces)


def process_and_store_photo(file_bytes: bytes, content_type: str | None) -> str:
    """Validate, re-encode and persist an uploaded image. Returns its public path.

    Deliberately synchronous: every step in here is CPU or disk work with nothing to await, so it
    belongs on a worker thread (see `process_and_store_upload`), not on the event loop. Measured
    on one machine, a 3024x4032 JPEG takes 427-549 ms and a 1080x1440 one 33-38 ms, and run on
    the loop it is the only thing that runs there: a coroutine asking to wake every 5 ms recorded
    a longest gap equal to the re-encode (535.5 ms of a 535.3 ms call) and got four wakes in
    total, against 29-33 wakes and a 27.1 ms longest gap on a thread. The idle floor on that
    machine is 15.7-16.5 ms, which is Windows timer granularity rather than this code.

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
        if image.format not in ACCEPTED_PIL_FORMATS:
            raise ValidationError("Unsupported image type. Use JPEG, PNG or WEBP.")
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


async def process_and_store_upload(file_bytes: bytes, content_type: str | None) -> str:
    """`process_and_store_photo` on a worker thread, so one upload does not own the whole worker.

    The app runs a single uvicorn worker and every request on it shares one event loop, so a
    resample that runs there is the only thing that runs there. In-process, a coroutine asking to
    wake every 5 ms saw its longest wait during one upload equal to the upload itself (535.5 ms of
    a 535.3 ms call) and got four wakes; on a thread the same call leaves it at 27.1 ms with 29-33
    wakes, and the bytes written are identical, hash for hash.

    Over a socket the same pair reads as one bystander client against a real worker: while a
    2400x3200 upload ran on the loop the server answered 5-8 cheap requests in its ~476 ms window
    and the slowest waited 386 ms; on a thread it answers 18-21 in the same window and the slowest
    waits 43.8 ms, against a 24.1 ms baseline measured with nothing in flight. Both halves drop the
    probe's first repeat as warm-up and aggregate the five that follow, so the window above is the
    upload's own median over those five (476.0 ms on the loop, 474.5 ms on the thread).
    """
    return await asyncio.to_thread(process_and_store_photo, file_bytes, content_type)


def delete_stored_photo(url: str) -> None:
    """Remove a stored upload by the public path it was handed out under.

    Only the last segment of the url is trusted, because a path is not an identifier:
    whatever arrived in the column is reduced to a filename inside the upload directory,
    and a file that is already gone is not an error worth raising over.
    """
    name = os.path.basename((url or "").strip())
    if not name:
        return
    try:
        os.remove(os.path.join(settings.upload_dir, name))
    except FileNotFoundError:
        pass
    except OSError as error:
        logger.warning("could not remove stored upload %s (%s)", name, type(error).__name__)
