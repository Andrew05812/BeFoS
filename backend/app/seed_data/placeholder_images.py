from __future__ import annotations

import math
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


# Curated duotone pairs — deterministic but intentional. Every pair runs deep at
# the top into a saturated mid-tone, so the monogram keeps contrast and the field
# never reads as grey or mud once the card's bottom scrim is layered over it.
_PALETTES: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((0x2B, 0x1E, 0x4F), (0xC6, 0x3B, 0x44)),  # iris night -> ember deep
    ((0x1A, 0x14, 0x33), (0xFF, 0x9A, 0x62)),  # midnight -> peach
    ((0x3A, 0x1C, 0x71), (0xB8, 0x5D, 0x6E)),  # plum -> rose
    ((0x38, 0x0F, 0x2A), (0xE0, 0x6A, 0x8E)),  # wine -> blush
    ((0x23, 0x25, 0x3A), (0x6C, 0x4C, 0xF1)),  # charcoal -> iris
    ((0x18, 0x1B, 0x4B), (0x5A, 0x8F, 0xE0)),  # indigo -> steel blue
    ((0x14, 0x32, 0x4A), (0x3E, 0x8E, 0x7E)),  # deep sea -> mint
    ((0x1F, 0x40, 0x37), (0x5F, 0xA8, 0x8B)),  # emerald
    ((0x2A, 0x12, 0x18), (0xF0, 0x54, 0x4F)),  # espresso -> ember
    ((0x10, 0x1B, 0x2E), (0x4E, 0x6D, 0xB5)),  # navy dusk
]


def _monogram(display_name: str) -> str:
    """Up to two initials, so a two-word name still reads as a person, not a glyph."""
    letters = [word[0] for word in display_name.split() if word[:1].isalpha()]
    return ("".join(letters[:2]) or "B").upper()


def _gradient(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    """Diagonal duotone ramp, rasterised on a coarse grid and upscaled.

    Drawing one line per pixel row left visible steps in the ramp; a smooth
    function sampled small and resampled with LANCZOS has no banding at all.
    """
    grid = 240
    span = 2 * (grid - 1)
    small = Image.new("RGB", (grid, grid))
    px = small.load()
    for row in range(grid):
        for col in range(grid):
            px[col, row] = _mix(c1, c2, ((col + row) / span) ** 1.12)
    return small.resize((_SIZE, _SIZE), Image.LANCZOS)


def _radial(cx: float, cy: float, radius: float, peak: int) -> Image.Image:
    """Gaussian falloff mask. Stacked solid ellipses banded into visible rings."""
    n = 150
    step = _SIZE / n
    small = Image.new("L", (n, n))
    px = small.load()
    for row in range(n):
        dy = (row + 0.5) * step - cy
        for col in range(n):
            dx = (col + 0.5) * step - cx
            d2 = (dx * dx + dy * dy) / (radius * radius)
            px[col, row] = max(0, min(255, int(peak * math.exp(-d2 * 2.2))))
    return small.resize((_SIZE, _SIZE), Image.BILINEAR)


def generate_avatar(seed_text: str, filename: str, display_name: str = "") -> str:
    """Create a deterministic duotone avatar carrying a restrained letter monogram.

    Returns /uploads path. Fully offline and safe: no external images, no real people.
    """
    os.makedirs(settings.upload_dir, exist_ok=True)
    h = sum(ord(c) for c in seed_text)
    c1, c2 = _PALETTES[h % len(_PALETTES)]

    img = _gradient(c1, c2)
    img.paste(Image.new("RGB", (_SIZE, _SIZE), (255, 255, 255)), (0, 0),
              _radial(_SIZE * 0.5, _SIZE * 0.32, _SIZE * 0.46, 40))
    img.paste(Image.new("RGB", (_SIZE, _SIZE), (0, 0, 0)), (0, 0),
              _radial(_SIZE * 0.5, _SIZE * 1.1, _SIZE * 0.9, 52))

    text = _monogram(display_name or seed_text)
    # The mark sits at 40% of the frame, inside a frosted disc — the same shape the
    # app draws when a user has no photo at all, so a seeded card and an empty one
    # read as one design system. The radius is what keeps it out of the way: on the
    # discovery card the score badge owns everything above a quarter of the frame
    # and the name plus interest chips own everything below its middle.
    cx, cy, radius = _SIZE * 0.5, _SIZE * 0.40, _SIZE * 0.105
    overlay = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    mark = ImageDraw.Draw(overlay)
    mark.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=(255, 255, 255, 30),
        outline=(255, 255, 255, 64),
        width=3,
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # PIL ignores alpha on an RGB canvas, so the glyph colour is pre-blended with the
    # local background washed by the disc instead of being painted translucent.
    local_bg = _mix(_mix(c1, c2, ((cx + cy) / (2 * _SIZE)) ** 1.12), (255, 255, 255), 30 / 255)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        draw.text(
            (cx, cy),
            text,
            fill=_mix(local_bg, (255, 255, 255), 0.72),
            anchor="mm",
            font=_font(78 if len(text) < 2 else 60),
        )
    except Exception:
        pass

    dest = os.path.join(settings.upload_dir, filename)
    img.save(dest, format="PNG")
    return f"/uploads/{filename}"
