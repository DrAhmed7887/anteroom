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
    return (
        max(0, int(bbox["left"] * w) - pad),
        max(0, int(bbox["top"] * h) - pad),
        min(w, int((bbox["left"] + bbox["width"]) * w) + pad),
        min(h, int((bbox["top"] + bbox["height"]) * h) + pad),
    )


def highlight(
    image_path: str | Path,
    boxes: list[dict],
    colour: tuple[int, int, int] = AMBER,
    dim: bool = True,
    max_width: int = 900,
) -> Image.Image:
    """Outline `boxes` on the document, dimming everything else so the eye lands
    on the evidence rather than hunting for it."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    if dim and boxes:
        veil = Image.new("RGB", (w, h), (255, 255, 255))
        img = Image.blend(img, veil, 0.55)
        original = Image.open(image_path).convert("RGB")
        for b in boxes:
            x0, y0, x1, y1 = _px(b, w, h, pad=6)
            img.paste(original.crop((x0, y0, x1, y1)), (x0, y0))

    d = ImageDraw.Draw(img)
    for b in boxes:
        x0, y0, x1, y1 = _px(b, w, h)
        for i in range(3):
            d.rectangle([x0 - i, y0 - i, x1 + i, y1 + i], outline=colour)

    if w > max_width:
        img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
    return img


def highlight_words(image_path: str | Path, words: list[dict], max_width: int = 900) -> Image.Image:
    """Colour every word by how well it was read. This is the confidence gate,
    made visible: green words survived, the red one was deleted."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    d = ImageDraw.Draw(img)
    for word in words:
        colour = STATE_COLOUR.get(word["state"], SLATE)
        x0, y0, x1, y1 = _px(word["bbox"], w, h, pad=2)
        width = 4 if word["state"] == "unreadable" else 2
        for i in range(width):
            d.rectangle([x0 - i, y0 - i, x1 + i, y1 + i], outline=colour)
    if w > max_width:
        img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
    return img
