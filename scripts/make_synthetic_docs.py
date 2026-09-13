"""Generate the three synthetic intake documents for the Anteroom demo.

Every document is fabricated. No real patient, clinician, or clinic is
represented. Each one carries a deliberate, specific flaw so the demo exercises
three different agent behaviours rather than three variations of "it worked":

  1. referral_letter  -- angled phone photo; clinically rich but NEVER states
                         the referral question. Blocking gap by omission.
  2. medication_list  -- genuine handwriting; the anticoagulant dose is truly
                         illegible. The agent must refuse to guess.
  3. screen_photo     -- photo of a monitor; glare eats the renal function
                         result. Partial extraction with honest gaps.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
OUT.mkdir(parents=True, exist_ok=True)

SERIF = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"
SERIF_BOLD = "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"
HAND = "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
SANS_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"

random.seed(7)
np.random.seed(7)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(SANS, size)


def paper(w: int, h: int, tint=(252, 251, 247)) -> Image.Image:
    """Off-white sheet with faint fibre noise so it does not read as a PDF."""
    img = Image.new("RGB", (w, h), tint)
    noise = np.random.normal(0, 3.2, (h, w, 3))
    arr = np.clip(np.array(img).astype(float) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _coeffs(src, dst):
    m = []
    for s, d in zip(src, dst):
        m.append([d[0], d[1], 1, 0, 0, 0, -s[0] * d[0], -s[0] * d[1]])
        m.append([0, 0, 0, d[0], d[1], 1, -s[1] * d[0], -s[1] * d[1]])
    A = np.array(m, dtype=float)
    B = np.array(src, dtype=float).reshape(8)
    return np.linalg.solve(A.T @ A, A.T @ B)


def perspective(img: Image.Image, strength: float = 0.045) -> Image.Image:
    """Tilt the sheet as if held at an angle over a desk."""
    w, h = img.size
    dx, dy = w * strength, h * strength * 0.6
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(dx * 1.4, dy), (w - dx * 0.3, dy * 0.35), (w - dx * 1.1, h - dy * 0.4), (dx * 0.5, h - dy)]
    canvas = Image.new("RGB", (w, h), (28, 28, 30))
    warped = img.transform((w, h), Image.PERSPECTIVE, _coeffs(src, dst), Image.BICUBIC)
    canvas.paste(warped, (0, 0))
    return canvas


def lighting(img: Image.Image, cx: float = 0.35, cy: float = 0.25, power: float = 1.5) -> Image.Image:
    """Uneven room light -- brighter near the window, falling off to a corner."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx / w) - cx) ** 2 + ((yy / h) - cy) ** 2)
    mask = np.clip(1.12 - (d ** power) * 0.85, 0.45, 1.15)[..., None]
    arr = np.clip(np.array(img).astype(float) * mask, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def glare(img: Image.Image, x0f, y0f, x1f, y1f, intensity=215) -> Image.Image:
    """A specular band -- the thing that actually destroys screen photos."""
    w, h = img.size
    band = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(band)
    d.polygon(
        [(w * x0f, h * y0f), (w * x1f, h * (y0f - 0.05)), (w * x1f, h * y1f), (w * x0f, h * (y1f + 0.05))],
        fill=intensity,
    )
    band = band.filter(ImageFilter.GaussianBlur(26))
    white = Image.new("RGB", (w, h), (255, 255, 255))
    img = Image.composite(white, img, band.point(lambda p: min(255, int(p * 1.35))))
    # Second, hotter core pass -- a real specular highlight clips to pure white.
    core = Image.new("L", (w, h), 0)
    ImageDraw.Draw(core).polygon(
        [(w * x0f, h * (y0f + 0.018)), (w * x1f, h * (y0f - 0.032)),
         (w * x1f, h * (y1f - 0.018)), (w * x0f, h * (y1f + 0.032))],
        fill=255,
    )
    core = core.filter(ImageFilter.GaussianBlur(15))
    return Image.composite(white, img, core)


def camera(img: Image.Image, blur=0.7, quality=72, path: Path | None = None) -> Image.Image:
    """Final pass: soften, add sensor grain, save through JPEG."""
    img = img.filter(ImageFilter.GaussianBlur(blur))
    arr = np.array(img).astype(float) + np.random.normal(0, 4.0, (img.size[1], img.size[0], 3))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = ImageEnhance.Contrast(img).enhance(1.04)
    if path:
        img.save(path, "JPEG", quality=quality)
    return img


def wrap(draw, text, fnt, x, y, max_w, line_h, fill=(30, 30, 38)):
    words, line = text.split(), ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            line = trial
        else:
            draw.text((x, y), line, font=fnt, fill=fill)
            y += line_h
            line = word
    if line:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
    return y


# ---------------------------------------------------------------- document 1
def referral_letter() -> Path:
    """Clinically detailed. Never actually asks a question. This is the single
    most common real-world referral defect and it is invisible to a summarizer
    that is only trying to be fluent."""
    W, H = 1240, 1754
    img = paper(W, H)
    d = ImageDraw.Draw(img)

    d.text((90, 96), "RIVERSIDE FAMILY PRACTICE", font=font(SERIF_BOLD, 34), fill=(20, 20, 28))
    d.text((90, 140), "14 Mill Lane  ·  Tel 0141 555 0182", font=font(SERIF, 22), fill=(85, 85, 95))
    d.line([(90, 182), (W - 90, 182)], fill=(120, 120, 130), width=2)

    d.text((90, 222), "Cardiology Department", font=font(SERIF, 24), fill=(30, 30, 38))
    d.text((90, 256), "Date: 11 September 2026", font=font(SERIF, 24), fill=(30, 30, 38))

    d.text((90, 320), "RE: Marta Ruiz Delgado    DOB 14/03/1958", font=font(SERIF_BOLD, 26), fill=(20, 20, 28))

    y = 384
    f = font(SERIF, 25)
    body = [
        "Dear Colleague,",
        "",
        "Thank you for seeing this pleasant 68-year-old lady who has been under our "
        "care for some years. She describes intermittent palpitations over the past "
        "four months, occurring perhaps two or three times per week, lasting several "
        "minutes and occasionally associated with light-headedness. There has been no "
        "frank syncope.",
        "",
        "Her background includes hypertension, type 2 diabetes and paroxysmal atrial "
        "fibrillation diagnosed in 2019. She is anticoagulated. Blood pressure in "
        "clinic last week was 148/86. She remains independent and continues to walk "
        "her dog daily without limitation.",
        "",
        "An ECG was performed at the surgery in March which I understand showed sinus "
        "rhythm at that time. Bloods were checked recently at the hospital.",
        "",
        "I would be grateful for your opinion.",
        "",
        "With many thanks,",
        "",
        "Dr A. Okafor",
        "General Practitioner",
    ]
    for para in body:
        if not para:
            y += 18
            continue
        y = wrap(d, para, f, 90, y, W - 180, 36)

    img = perspective(img, 0.05)
    img = lighting(img, 0.3, 0.2)
    p = OUT / "01_referral_letter.jpg"
    camera(img, blur=0.8, quality=74, path=p)
    return p


# ---------------------------------------------------------------- document 2
def medication_list() -> Path:
    """The hero document. The anticoagulant dose is destroyed beyond recovery --
    deliberately, and honestly. If a model returns a dose for line 3 it is
    hallucinating, and the demo depends on Anteroom refusing to."""
    W, H = 1100, 1500
    img = paper(W, H, tint=(250, 248, 238))
    d = ImageDraw.Draw(img)

    # faint ruled lines, like a notepad
    for i in range(9, H // 74):
        d.line([(70, i * 74), (W - 70, i * 74)], fill=(205, 212, 224), width=2)

    d.text((84, 92), "My tablets", font=font(HAND, 62), fill=(22, 34, 92))
    d.text((84, 176), "Marta  -  Sept 2026", font=font(HAND, 34), fill=(42, 54, 112))

    hand = font(HAND, 40)
    lines = [
        "1.  Ramipril  5mg  -  morning",
        "2.  Atorvastatin  40mg  -  at night",
        "3.  Apixaban      mg  twice a day",     # dose destroyed below
        "4.  Metformin  1g  twice a day",
        "5.  Bisoprolol  2.5mg  -  morning",
        "6.  Paracetamol  when needed",
    ]
    y = 300
    for i, line in enumerate(lines):
        jitter = random.randint(-4, 4)
        d.text((96, y + jitter), line, font=hand, fill=(24, 36, 96))
        if i == 2:
            dose_box = (int(96 + d.textlength("3.  Apixaban ", font=hand)), y - 10, 96 + 330, y + 56)
        y += 148

    d.text((96, y + 30), "(the pharmacy changed one of them", font=font(HAND, 32), fill=(24, 36, 96))
    d.text((96, y + 76), " but I wrote over it - sorry!)", font=font(HAND, 32), fill=(24, 36, 96))

    # Destroy the dose: ink bleed, overwriting, then heavy local blur.
    region = img.crop(dose_box)
    rd = ImageDraw.Draw(region)
    rw, rh = region.size
    for _ in range(14):
        x0, y0 = random.randint(0, rw - 30), random.randint(4, rh - 20)
        rd.line([(x0, y0), (x0 + random.randint(14, 46), y0 + random.randint(-14, 14))],
                fill=(30, 42, 104), width=random.randint(5, 10))
    rd.ellipse([rw * 0.28, rh * 0.18, rw * 0.62, rh * 0.86], fill=(46, 58, 118))
    region = region.filter(ImageFilter.GaussianBlur(7.5))
    img.paste(region, dose_box[:2])

    img = perspective(img, 0.035)
    img = lighting(img, 0.55, 0.15, power=1.3)
    p = OUT / "02_medication_list.jpg"
    camera(img, blur=0.9, quality=70, path=p)
    return p


# ---------------------------------------------------------------- document 3
def screen_photo() -> Path:
    """Gerhard's observation, rendered: reception photographs the monitor because
    the other system will not export. Glare takes out the renal result."""
    W, H = 1500, 1000
    screen = Image.new("RGB", (W, H), (238, 241, 246))
    d = ImageDraw.Draw(screen)

    d.rectangle([0, 0, W, 86], fill=(23, 52, 94))
    d.text((34, 28), "ST BRENDAN'S HOSPITAL   ·   Discharge Summary", font=font(SANS_BOLD, 30), fill=(255, 255, 255))
    d.text((W - 250, 30), "Record 4471-B", font=font(SANS, 24), fill=(186, 206, 232))

    d.rectangle([34, 116, W - 34, 206], fill=(255, 255, 255), outline=(206, 214, 226), width=2)
    d.text((54, 136), "RUIZ DELGADO, Marta", font=font(SANS_BOLD, 30), fill=(18, 22, 32))
    d.text((54, 172), "DOB 14/03/1958      Admitted 02/08/2026      Discharged 05/08/2026",
           font=font(SANS, 23), fill=(70, 78, 92))

    rows = [
        ("Reason for admission", "Fast atrial fibrillation with rapid ventricular response"),
        ("ECG on admission", "Atrial fibrillation, rate 148 bpm. No acute ischaemic change."),
        ("Echocardiogram", "LV function mildly impaired, EF 48%. Left atrium dilated."),
        ("Creatinine / eGFR", "Creatinine 118 umol/L    eGFR 44 mL/min/1.73m2"),
        ("Potassium", "4.2 mmol/L"),
        ("Anticoagulation", "Apixaban continued. Dose reduced on discharge - see TTO."),
        ("Follow-up", "Cardiology outpatients, 6 weeks. GP to check renal function."),
    ]
    y = 244
    for label, value in rows:
        d.text((54, y), label, font=font(SANS_BOLD, 23), fill=(48, 74, 122))
        wrap(d, value, font(MONO, 23), 420, y, W - 470, 30, fill=(24, 28, 38))
        y += 92
        d.line([(54, y - 24), (W - 54, y - 24)], fill=(224, 230, 240), width=1)

    # Monitor context: bezel, then the physics of photographing a screen.
    bez = 46
    frame = Image.new("RGB", (W + bez * 2, H + bez * 2), (26, 26, 30))
    frame.paste(screen, (bez, bez))
    d2 = ImageDraw.Draw(frame)
    d2.text((frame.size[0] // 2 - 40, H + bez + 10), "DELL", font=font(SANS_BOLD, 20), fill=(86, 86, 94))

    # Subtle scanline moire -- the tell that this is a photo of a display.
    arr = np.array(frame).astype(float)
    scan = (np.sin(np.arange(frame.size[1]) * 2.05) * 4.5)[:, None, None]
    frame = Image.fromarray(np.clip(arr + scan, 0, 255).astype(np.uint8))

    # Glare band positioned over the creatinine/eGFR row.
    frame = glare(frame, 0.02, 0.495, 1.0, 0.60, intensity=255)

    frame = perspective(frame, 0.038)
    frame = lighting(frame, 0.4, 0.3, power=1.2)
    p = OUT / "03_screen_photo.jpg"
    camera(frame, blur=1.0, quality=68, path=p)
    return p


if __name__ == "__main__":
    for fn in (referral_letter, medication_list, screen_photo):
        path = fn()
        size_kb = path.stat().st_size // 1024
        print(f"  {path.name:28s} {size_kb:>5d} KB")
    print(f"\nWritten to {OUT}")
