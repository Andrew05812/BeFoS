from __future__ import annotations

import os

from PIL import Image, ImageDraw

from app.core.config import settings

_SIZE = 600


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def generate_avatar(seed_text: str, filename: str) -> str:
    """Create a deterministic gradient avatar with an initial. Returns /uploads path.

    Fully offline and safe: no external images, no real people.
    """
    os.makedirs(settings.upload_dir, exist_ok=True)
    # Deterministic pseudo-colour from the seed text.
    h = sum(ord(c) for c in seed_text)
    c1 = ((h * 37) % 200, (h * 61) % 200, (h * 97) % 220)
    c2 = ((h * 53 + 40) % 220, (h * 29 + 80) % 200, (h * 71 + 120) % 200)

    img = Image.new("RGB", (_SIZE, _SIZE))
    draw = ImageDraw.Draw(img)
    for y in range(_SIZE):
        t = y / _SIZE
        draw.line(
            [(0, y), (_SIZE, y)],
            fill=(_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t)),
        )

    initial = (seed_text[:1] or "B").upper()
    try:
        font_size = 260
        draw.text((_SIZE / 2, _SIZE / 2), initial, fill=(255, 255, 255), anchor="mm")
    except Exception:
        pass

    dest = os.path.join(settings.upload_dir, filename)
    img.save(dest, format="PNG")
    return f"/uploads/{filename}"
