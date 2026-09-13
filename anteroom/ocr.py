"""Textract extraction and the confidence gate.

The gate is the reason this project is defensible. Textract reports a
confidence score for every word it reads; we turn that score into an explicit
state BEFORE any language model is involved, and we delete the text of anything
that falls below the floor.

That deletion is the point. On our demo document Textract reads the smudged
anticoagulant dose as the token "9" with 43% confidence. Apixaban is never
dosed at 9mg. Had we passed the raw transcript to a model, it would have
reported a confident, fabricated, clinically dangerous dose -- and nothing
downstream would have known. The model cannot make that mistake if the token
never reaches it.

Thresholds come from `docs/textract_probe_results.txt`, measured, not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import boto3

from .schemas import BBox, Confidence

# Measured on the demo corpus. A flat 90 cutoff was wrong: it would have
# flagged Metformin's dose (79.0) and "Bisoprolol" (69.1), both legible.
HIGH_FLOOR = 95.0
MEDIUM_FLOOR = 85.0
LOW_FLOOR = 60.0        # below this the text is discarded, not merely doubted

ILLEGIBLE = "⟪ILLEGIBLE⟫"


def state_for(confidence: float) -> Confidence:
    if confidence >= HIGH_FLOOR:
        return Confidence.HIGH
    if confidence >= MEDIUM_FLOOR:
        return Confidence.MEDIUM
    if confidence >= LOW_FLOOR:
        return Confidence.LOW
    return Confidence.UNREADABLE


@dataclass
class OcrWord:
    text: str
    confidence: float
    bbox: BBox

    @property
    def state(self) -> Confidence:
        return state_for(self.confidence)

    @property
    def safe_text(self) -> str:
        """What downstream is allowed to see. Unreadable words lose their text
        entirely -- a plausible wrong token is more dangerous than a hole."""
        return ILLEGIBLE if self.state == Confidence.UNREADABLE else self.text


@dataclass
class OcrLine:
    words: list[OcrWord]
    confidence: float
    bbox: BBox

    @property
    def raw_text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def safe_text(self) -> str:
        return " ".join(w.safe_text for w in self.words)

    @property
    def has_illegible(self) -> bool:
        return any(w.state == Confidence.UNREADABLE for w in self.words)

    def uncertain_words(self) -> list[OcrWord]:
        return [w for w in self.words if w.state in (Confidence.LOW, Confidence.UNREADABLE)]


@dataclass
class OcrDocument:
    document_id: str
    label: str
    source_path: Path
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def illegible_count(self) -> int:
        return sum(1 for ln in self.lines for w in ln.words if w.state == Confidence.UNREADABLE)

    def line_for(self, needle: str) -> OcrLine | None:
        needle = needle.lower()
        return next((ln for ln in self.lines if needle in ln.raw_text.lower()), None)

    def annotated_transcript(self) -> str:
        """The ONLY thing the language model receives. Never the image.

        Low-confidence words keep their text but are marked, so the model can
        report them with reduced confidence. Unreadable words are already gone.
        """
        out: list[str] = []
        for i, ln in enumerate(self.lines, 1):
            parts = []
            for w in ln.words:
                if w.state == Confidence.UNREADABLE:
                    parts.append(ILLEGIBLE)
                elif w.state == Confidence.LOW:
                    parts.append(f"{w.text}⟨?⟩")
                else:
                    parts.append(w.text)
            out.append(f"[L{i:02d}] {' '.join(parts)}")
        return "\n".join(out)


def _bbox(block: dict) -> BBox:
    g = block["Geometry"]["BoundingBox"]
    return BBox(left=g["Left"], top=g["Top"], width=g["Width"], height=g["Height"])


def read_document(
    path: Path | str,
    document_id: str,
    label: str,
    client=None,
    region: str = "us-east-1",
) -> OcrDocument:
    """Run Textract and apply the confidence gate in one pass."""
    path = Path(path)
    client = client or boto3.client("textract", region_name=region)
    resp = client.detect_document_text(Document={"Bytes": path.read_bytes()})

    blocks = {b["Id"]: b for b in resp["Blocks"]}
    doc = OcrDocument(document_id=document_id, label=label, source_path=path)

    for block in resp["Blocks"]:
        if block["BlockType"] != "LINE":
            continue
        word_ids = [i for rel in block.get("Relationships", []) for i in rel["Ids"]]
        words = [
            OcrWord(text=blocks[i]["Text"], confidence=blocks[i]["Confidence"], bbox=_bbox(blocks[i]))
            for i in word_ids
            if i in blocks and blocks[i]["BlockType"] == "WORD"
        ]
        if words:
            doc.lines.append(OcrLine(words=words, confidence=block["Confidence"], bbox=_bbox(block)))

    return doc
