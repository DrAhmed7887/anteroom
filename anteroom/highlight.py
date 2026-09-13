"""Draw the region a fact came from onto its source document.

Textract returns a normalised bounding box for every line and word it reads, so
a citation does not have to be taken on trust. The consultant clicks the fact
and sees the pixels. For the illegible dose this matters more than anywhere
else: the claim "we could not read this" is only credible if you can look at
what we could not read.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

AMBER = (245, 158, 11)
RED = (220, 38, 38)
GREEN = (16, 185, 129)
SLATE = (71, 85, 105)

STATE_COLOUR = {
    "high": GREEN,
    "medium": GREEN,
    "low": AMBER,
    "unreadable": RED,
}


def _px(bbox: dict, w: int, h: int, pad: int = 4) -> tuple[int, int, int, int]:
    left = max(0.0, float(bbox.get("left", 0)))
    top = max(0.0, float(bbox.get("top", 0)))
    width = max(0.0, float(bbox.get("width", 0)))
    height = max(0.0, float(bbox.get("height", 0)))
    x0 = max(0, int(left * w) - pad)
    y0 = max(0, int(top * h) - pad)
    x1 = min(w, max(x0, int((left + width) * w) + pad))
    y1 = min(h, max(y0, int((top + height) * h) + pad))
    return x0, y0, x1, y1


def highlight(
    image_path: str | Path,
    boxes: list[dict],
    colour: tuple[int, int, int] = AMBER,
    dim: bool = True,
    max_width: int = 900,
) -> Image.Image:
    """Outline `boxes` on the document, dimming everything else so the eye lands
    on the evidence rather than hunting for it."""
    with Image.open(image_path) as src:
        original = src.convert("RGB")
    w, h = original.size
    img = original.copy()

    if dim and boxes:
        veil = Image.new("RGB", (w, h), (255, 255, 255))
        img = Image.blend(img, veil, 0.55)
        for b in boxes:
            x0, y0, x1, y1 = _px(b, w, h, pad=6)
            if x1 > x0 and y1 > y0:
                img.paste(original.crop((x0, y0, x1, y1)), (x0, y0))

    d = ImageDraw.Draw(img)
    for b in boxes:
        x0, y0, x1, y1 = _px(b, w, h)
        for i in range(3):
            d.rectangle([x0 - i, y0 - i, x1 + i, y1 + i], outline=colour)

    if max_width > 0 and w > max_width:
        new_h = max(1, int(h * max_width / w))
        img = img.resize((max_width, new_h), Image.LANCZOS)
    return img


def highlight_words(image_path: str | Path, words: list[dict], max_width: int = 900) -> Image.Image:
    """Colour every word by how well it was read. This is the confidence gate,
    made visible: green words survived, the red one was deleted."""
    with Image.open(image_path) as src:
        img = src.convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    for word in words:
        colour = STATE_COLOUR.get(word.get("state"), SLATE)
        x0, y0, x1, y1 = _px(word.get("bbox", {}), w, h, pad=2)
        width = 4 if word.get("state") == "unreadable" else 2
        for i in range(width):
            d.rectangle([x0 - i, y0 - i, x1 + i, y1 + i], outline=colour)
    if max_width > 0 and w > max_width:
        new_h = max(1, int(h * max_width / w))
        img = img.resize((max_width, new_h), Image.LANCZOS)
    return img
