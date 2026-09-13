"""Tests for visual bounding-box and confidence gate highlighting."""

from pathlib import Path
from PIL import Image

from anteroom.highlight import AMBER, RED, GREEN, highlight, highlight_words


def test_highlight_draws_box_and_returns_valid_image(tmp_path: Path):
    # Create a small blank image
    img_path = tmp_path / "test_doc.png"
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    img.save(img_path)

    boxes = [{"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.05}]
    result = highlight(img_path, boxes, colour=RED, dim=True, max_width=600)

    assert isinstance(result, Image.Image)
    assert result.size[0] == 600  # Resized to max_width
    assert result.size[1] == 750  # Maintained aspect ratio


def test_highlight_handles_empty_boxes(tmp_path: Path):
    img_path = tmp_path / "test_blank.png"
    img = Image.new("RGB", (400, 500), color=(240, 240, 240))
    img.save(img_path)

    result = highlight(img_path, [], colour=AMBER, dim=False, max_width=900)
    assert isinstance(result, Image.Image)
    assert result.size == (400, 500)


def test_highlight_words_colors_words_by_state(tmp_path: Path):
    img_path = tmp_path / "test_words.png"
    img = Image.new("RGB", (600, 800), color=(255, 255, 255))
    img.save(img_path)

    words = [
        {"state": "high", "bbox": {"left": 0.1, "top": 0.1, "width": 0.1, "height": 0.02}},
        {"state": "unreadable", "bbox": {"left": 0.3, "top": 0.1, "width": 0.05, "height": 0.02}},
        {"state": "low", "bbox": {"left": 0.5, "top": 0.1, "width": 0.08, "height": 0.02}},
    ]

    result = highlight_words(img_path, words, max_width=600)
    assert isinstance(result, Image.Image)
    assert result.size == (600, 800)


def test_highlight_handles_out_of_bounds_boxes(tmp_path: Path):
    img_path = tmp_path / "test_oob.png"
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img.save(img_path)

    # Box with negative coordinates and extending past 1.0
    boxes = [{"left": -0.5, "top": -0.2, "width": 2.0, "height": 1.5}]
    result = highlight(img_path, boxes, colour=RED, dim=True, max_width=200)
    assert isinstance(result, Image.Image)
    assert result.size == (200, 200)


def test_highlight_words_applies_correct_colors(tmp_path: Path):
    img_path = tmp_path / "test_colors.png"
    # Black background so color drawing is obvious
    img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    img.save(img_path)

    words = [
        {"state": "unreadable", "bbox": {"left": 0.2, "top": 0.2, "width": 0.2, "height": 0.2}},
        {"state": "high", "bbox": {"left": 0.6, "top": 0.6, "width": 0.2, "height": 0.2}},
    ]
    result = highlight_words(img_path, words, max_width=100)

    pixels = {result.getpixel((x, y)) for x in range(100) for y in range(100)}
    assert RED in pixels, "Unreadable box border in RED must be drawn"
    assert GREEN in pixels, "High confidence box border in GREEN must be drawn"
