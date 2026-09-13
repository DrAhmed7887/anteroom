"""Regression coverage for a fully documented cardiology patient."""

from datetime import datetime

from anteroom.readiness import audit
from anteroom.schemas import (
    Confidence,
    DocumentMeta,
    ExtractedFact,
    IntakeRecord,
    Medication,
    ReadinessStatus,
    SourceRef,
)


def test_carlos_vega_with_complete_documents_is_ready():
    referral = SourceRef(
        document_id="carlos-referral",
        document_label="Referral letter",
        location="page 1",
    )
    medication_list = SourceRef(
        document_id="carlos-medications",
        document_label="Complete medication list",
        location="page 1",
    )
    ecg = SourceRef(
        document_id="carlos-ecg",
        document_label="12-lead ECG",
        location="page 1",
    )
    lab_results = SourceRef(
        document_id="carlos-labs",
        document_label="Recent renal function results",
        location="page 1",
    )

    record = IntakeRecord(
        patient_ref="Carlos Vega",
        appointment_at=datetime(2026, 9, 14, 14, 30),
        visit_type="cardiology_new_consult",
        documents=[
            DocumentMeta(
                document_id="carlos-referral",
                label="Referral letter",
                kind="referral_letter",
                capture_quality="good",
                received_at=datetime(2026, 9, 12, 9, 0),
            ),
            DocumentMeta(
                document_id="carlos-medications",
                label="Complete medication list",
                kind="medication_list",
                capture_quality="good",
                received_at=datetime(2026, 9, 12, 9, 1),
            ),
            DocumentMeta(
                document_id="carlos-ecg",
                label="12-lead ECG",
                kind="form",
                capture_quality="good",
                received_at=datetime(2026, 9, 12, 9, 2),
            ),
            DocumentMeta(
                document_id="carlos-labs",
                label="Recent renal function results",
                kind="discharge",
                capture_quality="good",
                received_at=datetime(2026, 9, 12, 9, 3),
            ),
        ],
        facts={
            "referral_question": ExtractedFact(
                field="referral_question",
                value="Assess palpitations and advise on management.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
            "current_medications": ExtractedFact(
                field="current_medications",
                value="Three medications listed with doses and frequencies.",
                confidence=Confidence.HIGH,
                source=medication_list,
            ),
            "anticoagulant_status": ExtractedFact(
                field="anticoagulant_status",
                value="Not taking anticoagulants.",
                confidence=Confidence.HIGH,
                source=medication_list,
            ),
            "recent_ecg": ExtractedFact(
                field="recent_ecg",
                value="2026-08-20; sinus rhythm, no acute changes.",
                confidence=Confidence.HIGH,
                source=ecg,
            ),
            "renal_function": ExtractedFact(
                field="renal_function",
                value="2026-08-20; creatinine 0.9 mg/dL, eGFR 94.",
                confidence=Confidence.HIGH,
                source=lab_results,
            ),
            "allergies": ExtractedFact(
                field="allergies",
                value="No known drug allergies.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
            "presenting_symptoms": ExtractedFact(
                field="presenting_symptoms",
                value="Intermittent palpitations without syncope.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
            "previous_echo": ExtractedFact(
                field="previous_echo",
                value="No previous echocardiogram.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
            "bp_diary": ExtractedFact(
                field="bp_diary",
                value="Not applicable; no diary supplied.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
            "family_history": ExtractedFact(
                field="family_history",
                value="No relevant family history.",
                confidence=Confidence.HIGH,
                source=referral,
            ),
        },
        medications=[
            Medication(
                name="Bisoprolol",
                dose="5 mg",
                frequency="once daily",
                confidence=Confidence.HIGH,
                source=medication_list,
            ),
            Medication(
                name="Lisinopril",
                dose="10 mg",
                frequency="once daily",
                confidence=Confidence.HIGH,
                source=medication_list,
            ),
            Medication(
                name="Atorvastatin",
                dose="20 mg",
                frequency="at night",
                confidence=Confidence.HIGH,
                source=medication_list,
            ),
        ],
    )

    report = audit(record)

    assert report.status == ReadinessStatus.READY
    assert report.score == 100
    assert report.gaps == []
