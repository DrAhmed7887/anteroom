"""The readiness auditor -- deterministic policy, no model involved.

This is deliberately not an LLM. Whether a consultation can proceed is a
clinical policy question with an auditable answer, and a judge (or a regulator,
or a consultant who disagrees) must be able to read the rule that produced any
given flag. The model reads documents. This decides what the gaps mean.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import yaml

from .schemas import (
    Confidence,
    ExtractedFact,
    Gap,
    IntakeRecord,
    Medication,
    ReadinessReport,
    ReadinessStatus,
    Role,
    Severity,
)

POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "visit_requirements.yaml"

# Score weights. Blocking gaps dominate: one of them means the slot is at risk,
# and no number of satisfied "nice to have" fields should mask that.
WEIGHTS = {Severity.BLOCKING: 25, Severity.IMPORTANT: 8, Severity.MINOR: 2}

# Fields reception can reasonably resolve with one phone call to the patient.
PATIENT_ANSWERABLE = {
    "current_medications",
    "allergies",
    "presenting_symptoms",
    "lesion_site",
    "lesion_duration",
    "past_medical_history",
    "social_history",
    "family_history",
    "family_history_skin_cancer",
    "sun_exposure_history",
    "bp_diary",
}

# Fields that require chasing another organisation, not the patient.
ORG_ANSWERABLE = {
    "referral_question": "the referring practice",
    "recent_ecg": "the referring practice",
    "renal_function": "the hospital laboratory",
    "previous_echo": "the hospital records department",
    "previous_biopsy_result": "the pathology laboratory",
    "immunosuppression_status": "the referring practice",
}

CALL_SCRIPTS = {
    "current_medications": (
        "Hello, this is the clinic calling about your appointment. Could you have your "
        "medicines in front of you and read me the name and dose on each box?"
    ),
    "allergies": (
        "Hello, calling from the clinic before your appointment. Can I check whether you "
        "have any drug allergies, and what happens when you take them?"
    ),
    "referral_question": (
        "Hello, calling from cardiology about a referral for a patient seen with you. The "
        "letter describes the history but does not say what you would like us to advise on. "
        "Could you tell me the specific question?"
    ),
    "renal_function": (
        "Hello, calling from the clinic. We have a discharge summary where the creatinine "
        "and eGFR are not legible. Could you confirm the most recent results?"
    ),
    "recent_ecg": (
        "Hello, calling from cardiology. Could you send through the most recent ECG trace "
        "for this patient, or confirm the date it was performed?"
    ),
}


def load_policy(path: Path | None = None) -> dict:
    return yaml.safe_load((path or POLICY_PATH).read_text())


def _owner_for(field: str) -> Role:
    if field in ORG_ANSWERABLE or field in PATIENT_ANSWERABLE:
        return Role.RECEPTION
    return Role.NURSE


def _script_for(field: str) -> str | None:
    return CALL_SCRIPTS.get(field)


def _action_for(field: str, reason: str) -> str:
    target = ORG_ANSWERABLE.get(field)
    pretty = field.replace("_", " ")
    if reason == "unreadable":
        where = target or "the patient"
        return f"Confirm {pretty} with {where} -- the document is present but not legible."
    if target:
        return f"Request {pretty} from {target} before the appointment."
    return f"Ask the patient for {pretty} when confirming the appointment."


def _fact_gap(field: str, severity: Severity, fact: ExtractedFact | None) -> Gap:
    """A required field is absent, or present but not trustworthy."""
    if fact is None:
        reason, source = "missing", None
    elif fact.confidence == Confidence.UNREADABLE:
        reason, source = "unreadable", fact.source
    else:
        reason, source = "low_confidence", fact.source

    return Gap(
        field=field,
        severity=severity,
        reason=reason,
        owner=_owner_for(field),
        action=_action_for(field, reason),
        call_script=_script_for(field),
        source=source,
    )


def classify_medication(name: str | None, high_risk_map: dict[str, str]) -> str | None:
    """Return the risk class for a drug name, or None. Policy decides this, not the model."""
    if not name:
        return None
    lowered = name.lower()
    for drug, drug_class in high_risk_map.items():
        if drug in lowered:
            return drug_class
    return None


def _medication_gaps(meds: list[Medication], high_risk_map: dict[str, str]) -> list[Gap]:
    """The case the whole product exists for.

    Three different situations that a flat "dose is empty" check would merge:
      - high-risk drug, dose unreadable -> BLOCKING, and it is a NURSE task.
        Confirming an anticoagulant dose is medicines reconciliation, which is
        clinical work. Reception should not be the last line of defence on it.
      - ordinary drug, dose unreadable  -> IMPORTANT, reception can phone.
      - ordinary drug, dose simply not written ("paracetamol when needed")
        -> MINOR. The patient did not omit it by accident and nobody should
        spend a phone call on it.
    """
    gaps: list[Gap] = []
    for med in meds:
        unreadable = med.confidence == Confidence.UNREADABLE
        if med.dose is not None and not unreadable:
            continue

        name = med.name or "an unnamed medication"
        risk_class = classify_medication(med.name, high_risk_map)

        if risk_class:
            severity, owner, reason = Severity.BLOCKING, Role.NURSE, ("unreadable" if unreadable else "missing")
            action = (
                f"Medicines reconciliation: confirm the current dose of {name}. Policy "
                f"classifies this as high-risk ({risk_class}); it must be confirmed against "
                f"a dispensing record or the prescriber, not estimated."
            )
        elif unreadable:
            severity, owner, reason = Severity.IMPORTANT, Role.RECEPTION, "unreadable"
            action = f"Confirm the dose of {name} with the patient before the appointment."
        else:
            severity, owner, reason = Severity.MINOR, Role.RECEPTION, "not_stated"
            action = f"No dose recorded for {name} (likely as-needed). Confirm at check-in."

        gaps.append(
            Gap(
                field=f"medication_dose:{name}",
                severity=severity,
                reason=reason,
                owner=owner,
                action=action,
                call_script=(
                    f"Hello, this is the clinic calling before your appointment. I can see "
                    f"{name} on your list but the dose isn't clear on the copy we have. "
                    f"Could you read me exactly what it says on the box?"
                    if reason == "unreadable"
                    else None
                ),
                source=med.source,
            )
        )
    return gaps


# Phrases in a document that assert a medication was CHANGED. Keyword matching,
# deliberately: this rule must be readable by a clinician who wants to argue with it.
CHANGE_LANGUAGE = (
    "dose reduced", "dose increased", "dose changed", "dose adjusted",
    "reduced on discharge", "increased on discharge", "switched", "titrated",
    "now taking", "changed to", "uptitrated", "downtitrated",
)


def _reconciliation_gaps(record: IntakeRecord, high_risk_map: dict[str, str]) -> list[Gap]:
    """Cross-document reconciliation: one document says a drug was changed, and
    no document in our possession states the resulting value.

    This is the gap a per-document summarizer structurally cannot find. Each
    document is individually unremarkable -- the discharge note reads as
    reassuring, the medication list reads as complete. Only holding both at once
    shows that the current dose of a high-risk drug is unknown to anyone here.
    """
    gaps: list[Gap] = []
    for fact_obj in record.facts.values():
        if not fact_obj.value:
            continue
        lowered = fact_obj.value.lower()
        if not any(phrase in lowered for phrase in CHANGE_LANGUAGE):
            continue

        for med in record.medications:
            if not med.name or med.name.lower() not in lowered:
                continue
            if med.dose is not None and med.confidence != Confidence.UNREADABLE:
                continue  # change is documented AND the current value is known
            risk_class = classify_medication(med.name, high_risk_map)
            gaps.append(
                Gap(
                    field=f"unreconciled_change:{med.name}",
                    severity=Severity.BLOCKING if risk_class else Severity.IMPORTANT,
                    reason="conflicting",
                    owner=Role.NURSE,
                    action=(
                        f"{med.name} was changed according to '{fact_obj.source.document_label}', "
                        f"but no document states the current dose. Two independent sources were "
                        f"checked and neither resolves it. Reconcile before the consultation."
                    ),
                    call_script=None,
                    source=fact_obj.source,
                )
            )
    return gaps


def _staleness_gaps(record: IntakeRecord, freshness: dict[str, int]) -> list[Gap]:
    """A result that exists but predates the window is not the same as having it."""
    gaps: list[Gap] = []
    for field, max_age_days in (freshness or {}).items():
        fact = record.facts.get(field)
        if fact is None or not fact.is_usable:
            continue  # absence is already handled as a missing-field gap
        dated = _parse_date(fact.value)
        if dated is None:
            continue
        age = record.appointment_at.replace(tzinfo=None) - dated
        if age > timedelta(days=max_age_days):
            gaps.append(
                Gap(
                    field=field,
                    severity=Severity.IMPORTANT,
                    reason="stale",
                    owner=Role.RECEPTION,
                    action=(
                        f"{field.replace('_', ' ').capitalize()} is {age.days} days old; policy "
                        f"expects within {max_age_days}. Request an up-to-date result."
                    ),
                    call_script=_script_for(field),
                    source=fact.source,
                )
            )
    return gaps


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%B %Y", "%Y-%m"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def audit(record: IntakeRecord, policy: dict | None = None) -> ReadinessReport:
    """Score one appointment against the policy for its visit type."""
    policy = policy or load_policy()
    rules = policy.get(record.visit_type)
    if rules is None:
        raise KeyError(
            f"No policy for visit type {record.visit_type!r}. "
            f"Known: {[k for k in policy if not k.startswith('_')]}"
        )

    gaps: list[Gap] = []
    for tier, severity in (
        ("blocking", Severity.BLOCKING),
        ("important", Severity.IMPORTANT),
        ("minor", Severity.MINOR),
    ):
        for field in rules.get(tier) or []:
            fact = record.facts.get(field)
            if fact is None or not fact.is_usable:
                gaps.append(_fact_gap(field, severity, fact))

    high_risk_map = policy["_global"]["high_risk_medications"]
    gaps += _medication_gaps(record.medications, high_risk_map)
    gaps += _reconciliation_gaps(record, high_risk_map)
    gaps += _staleness_gaps(record, rules.get("freshness_days") or {})

    # One clinical issue, one task. If cross-document reconciliation already
    # flagged a drug, the plain "dose unreadable" gap for that same drug is the
    # same problem stated less well -- drop it rather than double-penalising.
    reconciled = {g.field.split(":", 1)[1] for g in gaps if g.field.startswith("unreconciled_change:")}
    gaps = [
        g for g in gaps
        if not (g.field.startswith("medication_dose:") and g.field.split(":", 1)[1] in reconciled)
    ]

    penalty = sum(WEIGHTS[g.severity] for g in gaps)
    score = max(0, 100 - penalty)

    if any(g.severity == Severity.BLOCKING for g in gaps):
        status = ReadinessStatus.AT_RISK
    elif any(g.severity == Severity.IMPORTANT for g in gaps):
        status = ReadinessStatus.NEEDS_ACTION
    else:
        status = ReadinessStatus.READY

    return ReadinessReport(
        patient_ref=record.patient_ref,
        appointment_at=record.appointment_at,
        visit_type=record.visit_type,
        status=status,
        score=score,
        gaps=sorted(gaps, key=lambda g: (WEIGHTS[g.severity] * -1, g.field)),
    )
