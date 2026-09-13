"""Probe: what does Textract actually return for our three documents?

Run BEFORE designing the confidence gate. The threshold has to come from real
numbers, not from a guess about what OCR confidence looks like.
"""
from pathlib import Path
import boto3

DOCS = sorted((Path(__file__).resolve().parent.parent / "data" / "synthetic").glob("*.jpg"))
tx = boto3.client("textract", region_name="us-east-1")

for doc in DOCS:
    resp = tx.detect_document_text(Document={"Bytes": doc.read_bytes()})
    blocks = resp["Blocks"]
    lines = [b for b in blocks if b["BlockType"] == "LINE"]
    words = [b for b in blocks if b["BlockType"] == "WORD"]

    confs = sorted(w["Confidence"] for w in words)
    n = len(confs)
    pct = lambda p: confs[int(n * p)] if n else 0

    print(f"\n{'='*78}\n{doc.name}   {len(lines)} lines, {n} words")
    print(f"  confidence  min {confs[0]:.1f}  p5 {pct(.05):.1f}  p25 {pct(.25):.1f}  "
          f"median {pct(.5):.1f}  max {confs[-1]:.1f}")
    low = [w for w in words if w["Confidence"] < 90]
    print(f"  words < 90%: {len(low)}"
          + (f"  →  {[(w['Text'], round(w['Confidence'],1)) for w in low][:8]}" if low else ""))

    for ln in lines:
        txt = ln["Text"]
        if any(k in txt.lower() for k in ("apixaban", "creatinine", "egfr", "grateful",
                                          "opinion", "anticoag", "potassium")):
            kids = [w for w in words
                    if w["Id"] in {i for r in ln.get("Relationships", []) for i in r["Ids"]}]
            print(f"\n  ★ LINE: {txt!r}  (line conf {ln['Confidence']:.1f})")
            for w in kids:
                bar = "█" * int(w["Confidence"] / 10)
                print(f"      {w['Text']:<22} {w['Confidence']:6.2f}  {bar}")
