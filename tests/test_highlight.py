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
