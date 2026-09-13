"""Data contract for Anteroom.

Design rule that drives everything else: the agent must be able to say
"I could not read this" as a first-class value. An illegible anticoagulant
dose is NOT a missing field and it is NOT a guess -- it is its own state,
and it routes to a human. Nothing downstream is allowed to collapse
UNREADABLE into None.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    """How much the reader trusts a single extracted value."""

    HIGH = "high"          # clearly legible, unambiguous
    MEDIUM = "medium"      # legible but inferred from context
    LOW = "low"            # partially legible, plausible but shaky
    UNREADABLE = "unreadable"  # cannot be read -- never guess, always escalate


class Severity(str, Enum):
    BLOCKING = "blocking"    # consultation cannot usefully proceed
    IMPORTANT = "important"  # consultation degraded, fix if there is time
    MINOR = "minor"          # note it, do not chase it


class Role(str, Enum):
    RECEPTION = "reception"
    NURSE = "nurse"
    DOCTOR = "doctor"


class ReadinessStatus(str, Enum):
    READY = "ready"              # green: walk in and consult
    NEEDS_ACTION = "needs_action"  # amber: fixable before the appointment
    AT_RISK = "at_risk"          # red: slot will be wasted unless someone acts


class SourceRef(BaseModel):
    """Provenance. Every clinical statement must be traceable to a document."""

    document_id: str
    document_label: str = Field(description="Human phrase, e.g. 'Referral letter, Dr Okafor'")
    location: str = Field(description="Where in the document, e.g. 'page 1, line 3'")


class ExtractedFact(BaseModel):
    """One field read off one document."""

    field: str
    value: str | None = Field(
        default=None,
        description="The literal value read. MUST be None when confidence is UNREADABLE.",
    )
    confidence: Confidence
    source: SourceRef
    note: str | None = Field(
        default=None,
        description="Why it is unreadable or ambiguous. Required when confidence is LOW or UNREADABLE.",
    )

    @property
    def is_usable(self) -> bool:
        return self.value is not None and self.confidence in (Confidence.HIGH, Confidence.MEDIUM)


class Medication(BaseModel):
    """Medications get their own shape: the failure mode we care about is a
    legible drug name with an illegible dose, which a flat string would hide."""

    name: str | None = None
    dose: str | None = None
    frequency: str | None = None
    confidence: Confidence
    source: SourceRef
    note: str | None = None
    is_high_risk: bool = Field(
        default=False,
        description="Anticoagulant, insulin, chemotherapy, opioid, immunosuppressant, "
        "antiarrhythmic. Raises an unreadable dose from IMPORTANT to BLOCKING.",
    )


class DocumentMeta(BaseModel):
    document_id: str
    label: str
    kind: str = Field(description="referral_letter | medication_list | screen_photo | form | discharge")
    capture_quality: str = Field(description="good | angled | glare | blurred | partial")
    received_at: datetime


class IntakeRecord(BaseModel):
    """Everything Anteroom knows about one upcoming appointment."""

    patient_ref: str = Field(description="Pseudonymous reference. Never a real identifier in logs.")
    appointment_at: datetime
    visit_type: str = Field(description="Key into visit_requirements.yaml")
    documents: list[DocumentMeta] = Field(default_factory=list)
    facts: dict[str, ExtractedFact] = Field(
        default_factory=dict,
        description="Keyed by requirement field name so the auditor can check presence directly.",
    )
    medications: list[Medication] = Field(default_factory=list)


class Gap(BaseModel):
    """Something standing between this record and a useful consultation."""

    field: str
    severity: Severity
    reason: str = Field(description="missing | unreadable | conflicting | stale")
    owner: Role
    action: str = Field(description="The concrete thing that human should do")
    call_script: str | None = Field(
        default=None,
        description="Verbatim words for reception to say on the phone. The point of the "
        "product: hand over a script, not a hallucinated value.",
    )
    source: SourceRef | None = None


class ReadinessReport(BaseModel):
    """The output that actually changes someone's morning."""

    patient_ref: str
    appointment_at: datetime
    visit_type: str
    status: ReadinessStatus
    score: int = Field(ge=0, le=100)
    gaps: list[Gap] = Field(default_factory=list)
    doctor_brief: str = Field(
        default="",
        description="Short pre-visit brief. Only facts with usable confidence may appear here.",
    )

    @property
    def blocking_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.severity == Severity.BLOCKING]

    def gaps_for(self, role: Role) -> list[Gap]:
        return [g for g in self.gaps if g.owner == role]
