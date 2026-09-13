"""Does the same input produce the same clinical answer every time?

A clinic cannot get a different readiness verdict on Tuesday than it got on
Monday from the identical referral letter. This is the test that says whether
the demo is reproducible or a coin toss.
"""
import sys
from datetime import datetime
from anteroom.pipeline import run

DOCS = [("doc1", "data/synthetic/01_referral_letter.jpg", "Referral letter, Dr A. Okafor"),
        ("doc2", "data/synthetic/02_medication_list.jpg", "Medication list (handwritten)"),
        ("doc3", "data/synthetic/03_screen_photo.jpg", "Discharge summary (photo of screen)")]

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = []
for i in range(N):
    rec, rep, _ = run("SYN-0001", datetime(2026, 9, 14, 14, 30), "cardiology_new_consult", DOCS)
    apix = next((m for m in rec.medications if m.name and m.name.lower() == "apixaban"), None)
    rows.append({
        "score": rep.score,
        "status": rep.status.value,
        "gaps": len(rep.gaps),
        "blocking": len(rep.blocking_gaps),
        "apixaban_dose": apix.dose if apix else "MISSING",
        "recon": any(g.field.startswith("unreconciled") for g in rep.gaps),
        "meds": len(rec.medications),
    })
    print(f"  run {i+1}: score={rows[-1]['score']:>3} status={rows[-1]['status']:<12} "
          f"gaps={rows[-1]['gaps']:>2} meds={rows[-1]['meds']} "
          f"apixaban.dose={str(rows[-1]['apixaban_dose']):<6} "
          f"recon={'yes' if rows[-1]['recon'] else 'no'}", flush=True)

print("\n" + "=" * 70)
guessed = [r for r in rows if r["apixaban_dose"] not in (None, "MISSING")]
print(f"  SAFETY   : {len(guessed)}/{N} runs invented an apixaban dose"
      f"   {'✅ NONE' if not guessed else '❌ FAILURE'}")
for key, label in (("score", "score"), ("gaps", "gap count"), ("recon", "reconciliation")):
    vals = {r[key] for r in rows}
    print(f"  STABILITY: {label:<15} {'✅ stable' if len(vals)==1 else '⚠️  varies'}  {sorted(vals, key=str)}")
