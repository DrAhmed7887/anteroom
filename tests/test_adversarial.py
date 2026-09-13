"""Adversarial and cross-specialty tests.

Two things this suite exists to disprove:

  1. That Anteroom only works on cardiology. The demo corpus is cardiology, and
     a system tuned to its own demo is not a system. Every policy gets exercised.

  2. That it only works on well-formed input. Real intake is blank pages,
     upside-down scans, and letters that say nothing. None of that may crash a
     clinic's morning, and none of it may silently produce a green light.

No model runs here. If a guarantee only holds when an LLM cooperates, it is not
a guarantee.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from anteroom.agents import allowed_fields
from anteroom.evidence import heading_match, load_evidence, scan
from anteroom.mapping import (
    canonical_field,
    is_real_medication,
    is_real_referral_question,
    load_aliases,
    load_not_a_medication,
    load_vague_referral_phrases,
    sanitise_dose,
)
from anteroom.readiness import audit, load_policy
from anteroom.schemas import (
    Confidence,
    ExtractedFact,
    IntakeRecord,
    Medication,
    ReadinessStatus,
    Role,
    Severity,
    SourceRef,
)

SRC = SourceRef(document_id="d1", document_label="Referral letter", location="line 1")


def fact(field, value, conf=Confidence.HIGH):
    return ExtractedFact(field=field, value=value, confidence=conf, source=SRC)


def record(visit_type, facts=None, meds=None):
    return IntakeRecord(
        patient_ref="SYN-ADV",
        appointment_at=datetime(2026, 9, 14, 9, 0),
        visit_type=visit_type,
        facts=facts or {},
        medications=meds or [],
    )


@pytest.fixture(scope="module")
def policy():
    return load_policy()


@pytest.fixture(scope="module")
def ctx():
    return load_aliases(), set(allowed_fields()), load_evidence()


# ══════════════════════════════════════════════ dermatology

def _derm_facts(**overrides):
    base = {
        "referral_question": "Is this pigmented lesion on the left calf malignant?",
        "lesion_site": "Left calf, 12mm pigmented lesion",
        "lesion_duration": "Noticed 8 months ago, enlarging",
        "immunosuppression_status": "Renal transplant 2019, on tacrolimus",
        "previous_biopsy_result": "2026-03-14",
        "current_medications": "Tacrolimus, prednisolone",
        "allergies": "No known drug allergies",
        "sun_exposure_history": "Outdoor worker",
        "family_history_skin_cancer": "Mother had melanoma",
    }
    base.update(overrides)
    return {k: fact(k, v) for k, v in base.items() if v is not None}


def test_complete_dermatology_packet_is_ready():
    report = audit(record("dermatology_lesion_review", _derm_facts()))
    assert report.status == ReadinessStatus.READY
    assert report.gaps == []


def test_missing_lesion_site_blocks_a_dermatology_consult():
    """You cannot examine a lesion nobody located."""
    report = audit(record("dermatology_lesion_review", _derm_facts(lesion_site=None)))
    gap = next(g for g in report.gaps if g.field == "lesion_site")
    assert gap.severity == Severity.BLOCKING
    assert report.status == ReadinessStatus.AT_RISK


def test_missing_biopsy_result_is_important_not_blocking():
    """The clinic can still see the patient; it just sees them less informed."""
    report = audit(record("dermatology_lesion_review", _derm_facts(previous_biopsy_result=None)))
    gap = next(g for g in report.gaps if g.field == "previous_biopsy_result")
    assert gap.severity == Severity.IMPORTANT
    assert report.status == ReadinessStatus.NEEDS_ACTION


def test_stale_biopsy_is_flagged_separately_from_a_missing_one():
    """A result that predates the policy window is not the same as having it.
    Dermatology allows two years; this one is a decade old."""
    report = audit(record("dermatology_lesion_review",
                          _derm_facts(previous_biopsy_result="2015-01-04")))
    gap = next(g for g in report.gaps if g.field == "previous_biopsy_result")
    assert gap.reason == "stale"
    assert "days old" in gap.action


def test_missing_immunosuppression_status_is_raised():
    """A transplant patient on tacrolimus is a different risk tier for a skin
    lesion than an otherwise well adult, so its absence must be visible."""
    report = audit(record("dermatology_lesion_review",
                          _derm_facts(immunosuppression_status=None)))
    assert any(g.field == "immunosuppression_status" and g.severity == Severity.IMPORTANT
               for g in report.gaps)


def test_a_cardiology_field_is_not_demanded_of_a_dermatology_visit():
    """Policies must not leak into each other."""
    report = audit(record("dermatology_lesion_review", _derm_facts()))
    assert not any(g.field in ("recent_ecg", "anticoagulant_status", "renal_function")
                   for g in report.gaps)


# ══════════════════════════════════════════════ general practice

def test_general_new_patient_complete_packet_is_ready():
    facts = {k: fact(k, "documented") for k in
             ("referral_question", "current_medications", "allergies",
              "presenting_symptoms", "past_medical_history", "social_history",
              "family_history")}
    facts["referral_question"] = fact("referral_question",
                                      "Please advise on whether her fatigue warrants imaging")
    assert audit(record("general_new_patient", facts)).status == ReadinessStatus.READY


def test_demographic_fields_are_never_scored(policy):
    """Age and sex orient a clinician. They are not requirements, and their
    absence must never produce a task for anyone to chase."""
    demographics = set(policy["_global"]["demographic_fields"])
    report = audit(record("general_new_patient"))
    assert not (demographics & {g.field for g in report.gaps})


def test_demographics_are_extractable_even_though_unscored():
    assert {"patient_age", "patient_sex"} <= set(allowed_fields())


def test_unknown_visit_type_fails_loudly(policy):
    """Silently scoring an unknown specialty against the wrong policy is worse
    than refusing."""
    with pytest.raises(KeyError) as exc:
        audit(record("orthopaedics_knee_review"))
    assert "orthopaedics_knee_review" in str(exc.value)


# ══════════════════════════════════════════════ empty and malformed input

def test_a_completely_empty_transcript_does_not_crash(ctx):
    aliases, allowed, ev = ctx
    assert scan([], aliases, allowed, ev) == {}


def test_blank_and_whitespace_lines_yield_nothing(ctx):
    aliases, allowed, ev = ctx
    assert scan(["", "   ", "\t", "\n"], aliases, allowed, ev) == {}


def test_an_empty_record_is_at_risk_not_ready():
    """A blank page must never read as a green light. This is the failure that
    would actually hurt someone."""
    report = audit(record("cardiology_new_consult"))
    assert report.status == ReadinessStatus.AT_RISK
    assert report.score == 0
    assert report.blocking_gaps


def test_malformed_lines_do_not_invent_fields(ctx):
    aliases, allowed, ev = ctx
    junk = ["::::", "|||", "....", "###", "\x00\x01", "a" * 400,
            "12:30 14:00 09:15", "-- -- --", "?????"]
    found = scan(junk, aliases, allowed, ev)
    assert found == {}, f"junk produced fields: {found}"


def test_a_mid_sentence_colon_is_not_a_heading(ctx):
    aliases, allowed, _ = ctx
    for line in ["The clinic opens at 09:00 on Tuesday",
                 "She said: I have been unwell",
                 "Ratio: 1:2 dilution noted"]:
        assert heading_match(line, aliases, allowed) is None, line


def test_extremely_long_label_is_rejected_as_a_heading(ctx):
    aliases, allowed, _ = ctx
    assert heading_match("x" * 200 + ": value", aliases, allowed) is None


def test_unicode_and_accents_survive_field_resolution(ctx):
    aliases, allowed, _ = ctx
    assert canonical_field("Créatinine / eGFR", aliases, allowed) == "renal_function"


# ══════════════════════════════════════════════ polite courtesies

COURTESIES = [
    "For your kind attention",
    "Thank you for seeing this patient",
    "Please review",
    "Over to you",
    "Grateful for your opinion",
    "Please see and advise",
    "Your opinion would be appreciated",
]

REAL_QUESTIONS = [
    "Grateful for your opinion on whether she needs ablation for paroxysmal AF",
    "Is her apixaban dose appropriate given an eGFR of 44?",
    "Please advise whether this lesion requires excision or observation",
    "Thank you for seeing this patient; specifically, should we stop her metformin "
    "before the contrast study?",
]


@pytest.mark.parametrize("phrase", COURTESIES)
def test_a_courtesy_is_not_a_referral_question(phrase, policy):
    """These are the most common thing a referral letter says instead of asking
    a question. Accepting them satisfies a BLOCKING requirement while the
    consultant still has no idea why the patient is coming."""
    assert is_real_referral_question(phrase, load_vague_referral_phrases(policy)) is False


@pytest.mark.parametrize("phrase", REAL_QUESTIONS)
def test_a_courtesy_followed_by_a_real_question_is_accepted(phrase, policy):
    assert is_real_referral_question(phrase, load_vague_referral_phrases(policy)) is True


def test_empty_and_none_referral_questions_are_rejected(policy):
    vague = load_vague_referral_phrases(policy)
    for value in (None, "", "   "):
        assert is_real_referral_question(value, vague) is False


# ══════════════════════════════════════════════ dose and medication guards

@pytest.mark.parametrize("prose", [
    "Dose reduced on discharge",
    "see TTO",
    "as per previous",
    "unchanged",
    "titrate to response",
])
def test_prose_never_becomes_a_dose(prose):
    assert sanitise_dose(prose)[0] is None


@pytest.mark.parametrize("dose,expected", [
    ("100 micrograms", "100 micrograms"),
    ("2.5mg", "2.5mg"),
    ("1000 units", "1000 units"),
    ("2 puffs", "2 puffs"),
    ("10 mg/kg", "10 mg/kg"),
])
def test_real_doses_survive_verbatim(dose, expected):
    assert sanitise_dose(dose)[0] == expected


def test_a_drug_class_is_not_a_drug(policy):
    stop = load_not_a_medication(policy)
    for klass in ("anticoagulant", "antiplatelet", "medication", "unknown"):
        assert is_real_medication(klass, stop) is False
    for drug in ("Apixaban", "Tacrolimus", "Levothyroxine"):
        assert is_real_medication(drug, stop) is True


def test_high_risk_dose_gap_routes_to_a_clinical_role_in_every_specialty():
    """Whatever the specialty, an unreadable anticoagulant dose is clinical
    work and must not land in reception's queue."""
    for visit in ("cardiology_new_consult", "dermatology_lesion_review",
                  "general_new_patient"):
        rep = audit(record(visit, meds=[
            Medication(name="Warfarin", dose=None, confidence=Confidence.UNREADABLE, source=SRC)
        ]))
        gap = next(g for g in rep.gaps if g.field.endswith(":Warfarin"))
        assert gap.severity == Severity.BLOCKING
        assert gap.owner == Role.NURSE, f"{visit} routed a high-risk dose to {gap.owner}"


# ══════════════════════════════════ two-column layouts and result vs request

def test_a_label_on_one_line_finds_its_value_on_the_next(ctx):
    """How every two-column layout survives OCR. Textract reads the label cell
    and the value cell as separate lines, so 'ECG on admission' and 'Atrial
    fibrillation, rate 148' arrive unconnected."""
    aliases, allowed, ev = ctx
    lines = ["ECG on admission",
             "Atrial fibrillation. rate 148 bpm. No acute ischaemic change."]
    found = scan(lines, aliases, allowed, ev)
    assert "recent_ecg" in found
    assert found["recent_ecg"][2] == "label+value"
    assert "148" in found["recent_ecg"][1]


def test_two_consecutive_labels_do_not_pair(ctx):
    """A label followed by another label is a layout artefact, not a value."""
    aliases, allowed, ev = ctx
    found = scan(["Echocardiogram", "Anticoagulation"], aliases, allowed, ev)
    assert found.get("previous_echo", (None, None, None))[2] != "label+value"


def test_a_request_for_a_test_is_not_a_result(ctx):
    """'GP to check renal function' names the field and proves only that nobody
    has the number. Accepting it would mark renal function documented for a
    patient whose creatinine row was destroyed by glare -- hiding the exact gap
    this system exists to surface."""
    aliases, allowed, ev = ctx
    for request in ["Cardiology outpatients. 6 weeks. GP to check renal function.",
                    "Please repeat renal function in 3 months",
                    "Renal function awaited"]:
        assert "renal_function" not in scan([request], aliases, allowed, ev), request


def test_an_actual_renal_result_is_accepted(ctx):
    aliases, allowed, ev = ctx
    found = scan(["Creatinine 118 umol/L eGFR 44 mL/min/1.73m2"], aliases, allowed, ev)
    assert "renal_function" in found


def test_a_measurement_field_requires_a_measurement(ctx):
    """The field name alone is not evidence the test was done."""
    aliases, allowed, ev = ctx
    assert "renal_function" not in scan(["Renal function discussed with the patient"],
                                        aliases, allowed, ev)
