"""Render the architecture diagram.

The diagram's job is to make one thing obvious at a glance: where a language
model is allowed to act, and where it is not. Model steps are one colour,
deterministic steps another, and the colours are the legend.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "architecture.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

W, H = 1900, 1560
BG = (247, 249, 252)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
DET = (16, 132, 106)         # deterministic
DET_BG = (226, 247, 240)
MODEL = (109, 40, 217)       # a model acts here
MODEL_BG = (238, 232, 254)
AWS = (217, 119, 6)
AWS_BG = (254, 243, 199)
LINE = (148, 163, 184)
RED = (220, 38, 38)

SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"


def f(path, size):
    return ImageFont.truetype(path, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def box(x, y, w, h, title, lines, accent, fill, tag=None, mono_lines=None):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=fill, outline=accent, width=3)
    d.rectangle([x, y, x + 7, y + h], fill=accent)
    d.text((x + 24, y + 18), title, font=f(BOLD, 26), fill=INK)
    ty = y + 54
    for ln in lines:
        d.text((x + 24, ty), ln, font=f(SANS, 20), fill=(51, 65, 85))
        ty += 27
    for ln in (mono_lines or []):
        d.text((x + 24, ty), ln, font=f(MONO, 19), fill=accent)
        ty += 26
    if tag:
        tw = d.textlength(tag, font=f(BOLD, 15))
        d.rounded_rectangle([x + w - tw - 34, y + 16, x + w - 14, y + 42], radius=9, fill=accent)
        d.text((x + w - tw - 24, y + 21), tag, font=f(BOLD, 15), fill=(255, 255, 255))


def arrow(x1, y1, x2, y2, label=None, colour=LINE, label_colour=None):
    d.line([x1, y1, x2, y2], fill=colour, width=3)
    a = 9
    d.polygon([(x2, y2), (x2 - a, y2 - a - 3), (x2 + a, y2 - a - 3)], fill=colour)
    if label:
        d.text((x2 + 18, (y1 + y2) // 2 - 12), label, font=f(BOLD, 18),
               fill=label_colour or MUTED)


# ---- header
d.text((60, 44), "Anteroom", font=f(BOLD, 52), fill=INK)
d.text((60, 108), "Pre-visit readiness for small specialist clinics", font=f(SANS, 26), fill=MUTED)
d.line([(60, 152), (W - 60, 152)], fill=(226, 232, 240), width=2)

# ---- legend
lx = W - 640
for i, (c, bgc, lab) in enumerate([
    (DET, DET_BG, "Deterministic — no model"),
    (MODEL, MODEL_BG, "A language model acts here"),
    (AWS, AWS_BG, "AWS managed service"),
]):
    d.rounded_rectangle([lx, 52 + i * 34, lx + 22, 72 + i * 34], radius=5, fill=bgc, outline=c, width=2)
    d.text((lx + 34, 52 + i * 34), lab, font=f(SANS, 19), fill=(51, 65, 85))

CX, BW = 520, 860

# ---- inputs
box(60, 190, 380, 118, "Intake", ["Phone photos, scans,", "screen captures"], MUTED, (255, 255, 255))
box(W - 440, 190, 380, 118, "Schedule", ["Tomorrow's appointment", "list"], MUTED, (255, 255, 255))
arrow(250, 308, CX + 120, 356)
arrow(W - 250, 308, CX + BW - 120, 356)

y = 360
box(CX, y, BW, 132, "Amazon Textract  ·  DetectDocumentText",
    ["Returns a confidence score and bounding box for EVERY word."],
    AWS, AWS_BG, tag="AWS",
    mono_lines=["3.  Apixaban    9    twice  a  day", "              43.08%"])

y2 = y + 176
arrow(CX + BW // 2, y + 132, CX + BW // 2, y2)
box(CX, y2, BW, 132, "Confidence gate",
    ["Below 60% the text is DELETED, not doubted. 60–85% is marked."],
    DET, DET_BG, tag="NO MODEL",
    mono_lines=["3.  Apixaban  [ILLEGIBLE]  twice  a  day"])

y3 = y2 + 176
arrow(CX + BW // 2, y2 + 132, CX + BW // 2, y3, "text only — never pixels", MODEL, RED)
box(CX, y3, BW, 116, "Document Interpreter  ·  Strands Agent",
    ["Reports what a line MEANS. Never how certain it is,", "never how risky a drug is."],
    MODEL, MODEL_BG, tag="MODEL")

y4 = y3 + 158
arrow(CX + BW // 2, y3 + 116, CX + BW // 2, y4)
box(CX, y4, BW, 116, "Normalisation  ·  clinical synonyms, dose shapes, stoplists",
    ["Config a clinician can read and correct.", "Anyone can audit a YAML file. Nobody can audit a prompt."],
    DET, DET_BG, tag="NO MODEL")

y5 = y4 + 158
arrow(CX + BW // 2, y4 + 116, CX + BW // 2, y5)
box(CX, y5, BW, 116, "Readiness auditor  ·  visit_requirements.yaml",
    ["Decides severity and which human owns each gap.", "Every flag traces to a rule you can argue with."],
    DET, DET_BG, tag="NO MODEL")

# ---- outputs
oy = y5 + 190
arrow(CX + BW // 2, y5 + 116, CX + BW // 2, oy - 4)
for i, (name, sub) in enumerate([
    ("Reception", "call scripts"),
    ("Nurse", "clinical clarifications"),
    ("Clinician", "pre-visit brief"),
]):
    bx = CX - 200 + i * 430
    box(bx, oy, 390, 96, name, [sub], INK, (255, 255, 255))

d.text((70, oy + 14), "Authorisation", font=f(BOLD, 23), fill=INK)
d.text((70, oy + 46), "enforced on every read", font=f(SANS, 18), fill=MUTED)
d.text((70, oy + 72), "+ audit log", font=f(SANS, 18), fill=MUTED)

# ---- footer claim
fy = oy + 150
d.line([(60, fy), (W - 60, fy)], fill=(226, 232, 240), width=2)
d.text((60, fy + 26), "The model never sees the image. It cannot infer a dose from a smudge "
                      "it was never shown.", font=f(BOLD, 27), fill=INK)
d.text((60, fy + 68), "Synthetic data only. Anteroom does not diagnose, prescribe, or assess "
                      "urgency.", font=f(SANS, 21), fill=MUTED)

img.save(OUT, "PNG")
print(f"  wrote {OUT}  ({OUT.stat().st_size // 1024} KB, {W}x{H})")
