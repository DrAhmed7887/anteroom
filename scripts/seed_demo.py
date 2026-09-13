"""Build the demo practice and pre-compute both patients.

Results are cached so the console opens instantly. Re-running Textract and the
interpreter on every page interaction would make the demo slow and the cost
pointless -- the pipeline is deterministic enough that a cached run is an
honest representation of a live one. `--fresh` recomputes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anteroom.brief import compose
from anteroom.pipeline import run
from anteroom.schemas import Role
from anteroom.store import STORE_DIR, Appointment, Practice, User, save_seed

PRACTICE = Practice(
    practice_id="northgate",
    name="Northgate Specialist Clinic",
    address="8 Northgate Road, Manchester M3 1PQ",
    specialty="Cardiology and General Medicine",
)

USERS = [
    User(user_id="u-admin", name="Priya Raman", role=Role.ADMIN, practice_id="northgate"),
    User(user_id="u-recep", name="Jo Adeyemi", role=Role.RECEPTION, practice_id="northgate"),
    User(user_id="u-nurse", name="Sister Claire Boateng", role=Role.NURSE, practice_id="northgate"),
    User(user_id="u-doc", name="Dr Amara Hale", role=Role.DOCTOR, practice_id="northgate"),
    # Belongs to a different practice. Exists purely so the console can
    # demonstrate that cross-practice access is refused, not merely hidden.
    User(user_id="u-outsider", name="Dr Mark Ferris", role=Role.DOCTOR, practice_id="riverside"),
]

CASES = [
    {
        "appointment_id": "apt-001",
        "patient_ref": "SYN-0001",
        "patient_display": "Marta Ruiz Delgado",
        "appointment_at": datetime(2026, 9, 14, 14, 30),
        "visit_type": "cardiology_new_consult",
        "clinician": "Dr Amara Hale",
        "documents": [
            ("doc1", "data/synthetic/01_referral_letter.jpg", "Referral letter, Dr A. Okafor"),
            ("doc2", "data/synthetic/02_medication_list.jpg", "Medication list (handwritten)"),
            ("doc3", "data/synthetic/03_screen_photo.jpg", "Discharge summary (photo of screen)"),
        ],
    },
    {
        "appointment_id": "apt-002",
        "patient_ref": "SYN-0002",
        "patient_display": "Thomas Whitfield",
        "appointment_at": datetime(2026, 9, 14, 10, 0),
        "visit_type": "general_new_patient",
        "clinician": "Dr Amara Hale",
        "documents": [
            ("doc4", "data/synthetic/04_clean_referral.jpg", "Referral letter, Dr S. Ellery"),
        ],
    },
    {
        "appointment_id": "apt-003",
        "patient_ref": "SYN-0003",
        "patient_display": "Tariq Al-Mansoor",
        "appointment_at": datetime(2026, 9, 14, 11, 30),
        "visit_type": "cardiology_new_consult",
        "clinician": "Dr Amara Hale",
        "documents": [
            ("doc5", "data/synthetic/05_international_referral.jpg", "Referral letter, Dr F. MacLeod (SI Units / DD/MM/YY)"),
        ],
    },
]


def main(fresh: bool = False) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    appointments = []

    for case in CASES:
        appointments.append(Appointment(
            appointment_id=case["appointment_id"],
            practice_id=PRACTICE.practice_id,
            patient_ref=case["patient_ref"],
            patient_display=case["patient_display"],
            appointment_at=case["appointment_at"],
            visit_type=case["visit_type"],
            clinician=case["clinician"],
            document_ids=[d[0] for d in case["documents"]],
        ))

        cache = STORE_DIR / f"{case['appointment_id']}.json"
        if cache.exists() and not fresh:
            print(f"  {case['patient_display']:<22} cached")
            continue

        print(f"  {case['patient_display']:<22} running pipeline…", flush=True)
        record, report, ocr_docs = run(
            case["patient_ref"], case["appointment_at"], case["visit_type"], case["documents"]
        )
        brief = compose(record, report)
        cache.write_text(json.dumps({
            "record": record.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "brief": brief.model_dump(mode="json"),
            "documents": [
                {
                    "document_id": d.document_id,
                    "label": d.label,
                    "path": str(d.source_path),
                    "illegible_count": d.illegible_count,
                    "lines": [
                        {
                            "text": ln.safe_text,
                            "raw": ln.raw_text,
                            "confidence": ln.confidence,
                            "bbox": ln.bbox.model_dump(),
                            "words": [
                                {"text": w.text, "safe": w.safe_text,
                                 "confidence": w.confidence, "state": w.state.value,
                                 "bbox": w.bbox.model_dump()}
                                for w in ln.words
                            ],
                        }
                        for ln in d.lines
                    ],
                }
                for d in ocr_docs
            ],
            "computed_at": datetime.now().isoformat(),
        }, indent=2))
        print(f"    -> {report.status.value} {report.score}/100, {len(report.gaps)} gaps")

    save_seed(PRACTICE, USERS, appointments)
    print(f"\n  seeded {PRACTICE.name}: {len(USERS)} users, {len(appointments)} appointments")


if __name__ == "__main__":
    main(fresh="--fresh" in sys.argv)
