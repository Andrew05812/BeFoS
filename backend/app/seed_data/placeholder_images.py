from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings

_SIZE = 600

# PIL's built-in bitmap font cannot render Cyrillic; prefer a real TTF.
# DejaVuSans-Bold (freely licensed) is vendored next to this module.
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t))


# Curated duotone pairs — deterministic but intentional, never garish random RGB.
_PALETTES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0x2B, 0x1E, 0x4F), (0xC6, 0x3B, 0x44)),  # iris night -> ember deep
    ((0x14, 0x32, 0x4A), (0x3E, 0x8E, 0x7E)),  # deep sea -> mint
    ((0x3A, 0x1C, 0x71), (0xB8, 0x5D, 0x6E)),  # plum -> rose
    ((0x23, 0x25, 0x3A), (0x6C, 0x4C, 0xF1)),  # charcoal -> iris
    ((0x42, 0x27, 0x5A), (0x73, 0x4B, 0x6D)),  # purple haze
    ((0x1F, 0x40, 0x37), (0x5F, 0xA8, 0x8B)),  # emerald
    ((0x42, 0x27, 0x13), (0xA8, 0x8F, 0x79)),  # cocoa sand
    ((0x35, 0x5C, 0x7D), (0x6C, 0x5B, 0x7B)),  # denim dusk
    ((0x2A, 0x08, 0x45), (0x4E, 0x7D, 0xB5)),  # violet -> steel blue
    ((0x0F, 0x20, 0x27), (0x3A, 0x5C, 0x66)),  # abyss
]


def generate_avatar(seed_text: str, filename: str) -> str:
    """Create a deterministic gradient avatar with a watermark initial.

    Returns /uploads path. Fully offline and safe: no external images, no real people.
    """
    os.makedirs(settings.upload_dir, exist_ok=True)
    h = sum(ord(c) for c in seed_text)
    top, bottom = _PALETTES[h % len(_PALETTES)]

    img = Image.new("RGB", (_SIZE, _SIZE))
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(_SIZE):
        t = (y / _SIZE) ** 1.25  # ease-in: darker band up top, colour pools low
        draw.line([(0, y), (_SIZE, y)], fill=_mix(top, bottom, t))

    # Soft halo behind the initial for depth.
    cx, cy = _SIZE * 0.5, _SIZE * 0.44
    for r, a in ((250, 14), (190, 16), (135, 18)):
        draw.ellipse([cx - r, cy - r * 1.12, cx + r, cy + r * 1.12], fill=(255, 255, 255, a))

    # PIL ignores text alpha on RGB canvases — pre-blend the watermark colour
    # with the local background instead.
    local_bg = _mix(top, bottom, (cy / _SIZE) ** 1.25)
    initial = (seed_text[:1] or "B").upper()
    try:
        draw.text((cx, cy), initial, fill=_mix(local_bg, (255, 255, 255), 0.24), anchor="mm", font=_font(340))
    except Exception:
        pass

    dest = os.path.join(settings.upload_dir, filename)
    img.save(dest, format="PNG")
    return f"/uploads/{filename}"
