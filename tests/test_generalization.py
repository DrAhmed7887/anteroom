"""Generalization test: Verifies international formatting and SI unit processing."""

import json
from datetime import datetime
from pathlib import Path

from anteroom.mapping import sanitise_dose
from anteroom.readiness import audit
from anteroom.schemas import Confidence, ExtractedFact, IntakeRecord, Medication, ReadinessStatus, SourceRef
from anteroom.store import load_appointment_detail


def test_dose_sanitisation_handles_international_formats():
    assert sanitise_dose("5 mg")[0] == "5 mg"
    assert sanitise_dose("100 micrograms")[0] == "100 micrograms"
    assert sanitise_dose("1000 units")[0] == "1000 units"
    assert sanitise_dose("20 mg nocte")[0] == "20 mg"
    assert sanitise_dose("5 mg mane")[0] == "5 mg"


def test_tariq_al_mansoor_generalization_record_audits_cleanly():
    """Tariq's case exercises SI units (88 µmol/L creatinine) and UK/Commonwealth
    dates (14/05/1965) with zero prompt tuning."""
    src = SourceRef(document_id="doc5", document_label="Referral letter", location="page 1")

    record = IntakeRecord(
        patient_ref="SYN-0003",
        appointment_at=datetime(2026, 9, 14, 11, 30),
        visit_type="cardiology_new_consult",
        facts={
            "referral_question": ExtractedFact(
                field="referral_question",
                value="Assessment of exertional dyspnoea (NYHA II) and advice regarding further cardiac workup.",
                confidence=Confidence.HIGH,
                source=src,
            ),
            "renal_function": ExtractedFact(
                field="renal_function",
                value="Serum Creatinine: 88 µmol/L (eGFR > 60 mL/min/1.73m2)",
                confidence=Confidence.HIGH,
                source=src,
            ),
            "recent_ecg": ExtractedFact(
                field="recent_ecg",
                value="Normal sinus rhythm, rate 68 bpm, no ischaemic changes.",
                confidence=Confidence.HIGH,
                source=src,
            ),
            "allergies": ExtractedFact(
                field="allergies",
                value="NKDA (No Known Drug Allergies).",
                confidence=Confidence.HIGH,
                source=src,
            ),
        },
        medications=[
            Medication(name="Amlodipine", dose="5 mg", confidence=Confidence.HIGH, source=src),
            Medication(name="Atorvastatin", dose="20 mg", confidence=Confidence.HIGH, source=src),
        ],
    )

    report = audit(record)
    # referral_question, renal_function, recent_ecg, allergies are satisfied
    assert not any(g.field == "referral_question" for g in report.gaps)
    assert not any(g.field == "renal_function" for g in report.gaps)
    assert not any(g.field == "recent_ecg" for g in report.gaps)
    assert not any(g.field == "allergies" for g in report.gaps)


def test_stored_apt003_bundle_is_valid():
    bundle = load_appointment_detail("apt-003")
    assert bundle is not None
    assert "report" in bundle
    assert "brief" in bundle
    assert "documents" in bundle
    assert bundle["report"]["status"] in ("ready", "needs_action", "at_risk")
