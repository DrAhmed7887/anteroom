"""Golden-record tests.

`marta_record()` is what the document reader MUST produce from the three
synthetic documents. It is written by hand here, before the reader exists, so
the extraction work has a target to hit rather than a vibe to approximate.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from anteroom.readiness import audit, classify_medication, load_policy
from anteroom.schemas import (
    Confidence,
    DocumentMeta,
    ExtractedFact,
    IntakeRecord,
    Medication,
    ReadinessStatus,
    Role,
    Severity,
    SourceRef,
)

REFERRAL = SourceRef(document_id="doc1", document_label="Referral letter, Dr A. Okafor", location="page 1")
MEDLIST = SourceRef(document_id="doc2", document_label="Patient medication list (handwritten)", location="line 3")
SCREEN = SourceRef(document_id="doc3", document_label="Discharge summary (photo of screen)", location="Creatinine / eGFR row")


def fact(field, value, conf=Confidence.HIGH, src=REFERRAL, note=None):
    return ExtractedFact(field=field, value=value, confidence=conf, source=src, note=note)


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def marta_record() -> IntakeRecord:
    return IntakeRecord(
        patient_ref="SYN-0001",
        appointment_at=datetime(2026, 9, 14, 14, 30),
        visit_type="cardiology_new_consult",
        documents=[
            DocumentMeta(document_id="doc1", label="Referral letter", kind="referral_letter",
                         capture_quality="angled", received_at=datetime(2026, 9, 12, 9, 14)),
            DocumentMeta(document_id="doc2", label="Medication list", kind="medication_list",
                         capture_quality="blurred", received_at=datetime(2026, 9, 12, 9, 15)),
            DocumentMeta(document_id="doc3", label="Discharge summary", kind="screen_photo",
                         capture_quality="glare", received_at=datetime(2026, 9, 12, 9, 16)),
        ],
        facts={
            # The letter is clinically rich but never asks a question -> absent entirely.
            "presenting_symptoms": fact("presenting_symptoms", "Intermittent palpitations, 4 months, 2-3x/week, with light-headedness. No syncope."),
            "anticoagulant_status": fact("anticoagulant_status", "On apixaban; dose reduced at discharge 05/08/2026", src=SCREEN),
            "recent_ecg": fact("recent_ecg", "2026-08-02", src=SCREEN, note="AF, rate 148 bpm, no acute ischaemic change"),
            "previous_echo": fact("previous_echo", "EF 48%, mildly impaired LV, dilated LA", src=SCREEN),
            "current_medications": fact("current_medications", "6 medications listed by patient", src=MEDLIST),
            # Glare destroyed the renal row -- present as a document, absent as a value.
            "renal_function": ExtractedFact(
                field="renal_function", value=None, confidence=Confidence.UNREADABLE, source=SCREEN,
                note="Specular glare across the creatinine/eGFR row; no digits recoverable.",
            ),
        },
        medications=[
            Medication(name="Ramipril", dose="5mg", frequency="morning", confidence=Confidence.HIGH, source=MEDLIST),
            Medication(name="Atorvastatin", dose="40mg", frequency="at night", confidence=Confidence.HIGH, source=MEDLIST),
            Medication(name="Apixaban", dose=None, frequency="twice a day", confidence=Confidence.UNREADABLE,
                       source=MEDLIST, note="Dose overwritten by the patient and illegible."),
            Medication(name="Metformin", dose="1g", frequency="twice a day", confidence=Confidence.HIGH, source=MEDLIST),
            Medication(name="Bisoprolol", dose="2.5mg", frequency="morning", confidence=Confidence.HIGH, source=MEDLIST),
            Medication(name="Paracetamol", dose=None, frequency="when needed", confidence=Confidence.HIGH, source=MEDLIST),
        ],
    )


def test_policy_classifies_risk_not_the_model(policy):
    hrm = policy["_global"]["high_risk_medications"]
    assert classify_medication("Apixaban", hrm) == "anticoagulant"
    assert classify_medication("Paracetamol", hrm) is None


def test_marta_is_at_risk(marta_record):
    r = audit(marta_record)
    assert r.status == ReadinessStatus.AT_RISK
    assert 20 <= r.score <= 40, f"score {r.score} should read as 'well documented but blocked'"


def test_missing_referral_question_blocks(marta_record):
    r = audit(marta_record)
    g = next(g for g in r.gaps if g.field == "referral_question")
    assert g.severity == Severity.BLOCKING
    assert g.reason == "missing"
    assert g.owner == Role.RECEPTION
    assert g.call_script and "what you would like us to advise on" in g.call_script


def test_illegible_anticoagulant_dose_blocks_and_is_never_guessed(marta_record):
    """The centre of the product. An unreadable dose on a high-risk drug must
    block, must route to a clinical human, and must carry no value at all."""
    r = audit(marta_record)
    g = next(g for g in r.gaps if g.field.endswith(":Apixaban"))
    assert g.severity == Severity.BLOCKING
    assert g.owner == Role.NURSE, "anticoagulant reconciliation is clinical work, not reception work"
    apixaban = next(m for m in marta_record.medications if m.name == "Apixaban")
    assert apixaban.dose is None


def test_cross_document_reconciliation_finds_what_no_single_document_shows(marta_record):
    """The discharge summary says the dose was reduced. The medication list's
    dose is illegible. Each document alone looks fine; together they prove the
    current dose is unknown to anyone in the building."""
    r = audit(marta_record)
    g = next(g for g in r.gaps if g.field == "unreconciled_change:Apixaban")
    assert g.severity == Severity.BLOCKING
    assert g.reason == "conflicting"
    assert g.owner == Role.NURSE
    assert "neither resolves it" in g.action
    # The weaker, duplicate gap for the same drug must have been absorbed.
    assert not any(x.field == "medication_dose:Apixaban" for x in r.gaps)


def test_as_needed_medication_without_a_dose_is_only_a_note(marta_record):
    """'Paracetamol when needed' is not a failure of extraction and must not
    consume a phone call."""
    r = audit(marta_record)
    g = next(g for g in r.gaps if g.field.startswith("medication_dose:Paracetamol"))
    assert g.severity == Severity.MINOR
    assert g.reason == "not_stated"
    assert g.call_script is None


def test_work_is_split_across_roles(marta_record):
    """Three queues must actually be three queues."""
    r = audit(marta_record)
    assert r.gaps_for(Role.NURSE), "nurse queue should not be empty"
    assert r.gaps_for(Role.RECEPTION), "reception queue should not be empty"


def test_glared_renal_result_is_unreadable_not_missing(marta_record):
    r = audit(marta_record)
    g = next(g for g in r.gaps if g.field == "renal_function")
    assert g.reason == "unreadable"
    assert g.source and "screen" in g.source.document_label.lower()


def test_doctor_brief_contains_only_usable_facts(marta_record):
    """Nothing with UNREADABLE confidence may ever reach the clinician as fact."""
    assert marta_record.facts["renal_function"].is_usable is False
    assert marta_record.facts["presenting_symptoms"].is_usable is True


def test_a_complete_record_reads_ready(marta_record):
    """Control case: fill every gap and the same policy must return green."""
    rec = marta_record.model_copy(deep=True)
    rules = load_policy()["cardiology_new_consult"]
    for field in rules["blocking"] + rules["important"] + rules["minor"]:
        rec.facts[field] = fact(field, "documented")
    rec.facts["recent_ecg"] = fact("recent_ecg", "2026-08-02", src=SCREEN)
    rec.facts["renal_function"] = fact("renal_function", "2026-08-02", src=SCREEN)
    for m in rec.medications:
        m.dose, m.confidence = m.dose or "as directed", Confidence.HIGH
    r = audit(rec)
    assert r.status == ReadinessStatus.READY
    assert r.score == 100
    assert r.gaps == []
