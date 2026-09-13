"""What the interpreter agent is allowed to return.

Note what is absent: confidence. The model reports *semantics* -- which line
holds the allergy list, which token is a drug name. It never reports certainty.
Certainty is owned by the OCR confidence gate, which measured it before the
model was involved. Letting a language model grade its own reliability is the
mistake this whole design exists to avoid.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# Models emit "null", "none", "N/A", "unknown" as STRINGS with dismaying
# regularity. Amazon Nova Pro did exactly that for the illegible apixaban dose
# in testing -- returning the string "null", which is truthy, and would have
# sailed past an `is not None` check straight into a clinical brief as a known
# value. The gate upstream is the real defence; this is the second one.
NULL_SENTINELS = {
    "", "null", "none", "nil", "n/a", "na", "unknown", "not stated", "not specified",
    "illegible", "unreadable", "not legible", "undefined", "-", "--", "?",
}


def _null_if_sentinel(v: str | None) -> str | None:
    if v is None:
        return None
    cleaned = str(v).strip()
    if cleaned.lower() in NULL_SENTINELS or "⟪ILLEGIBLE⟫" in cleaned:
        return None
    return cleaned


class ExtractedMedication(BaseModel):
    name: str = Field(description="Drug name exactly as written in the transcript.")
    dose: str | None = Field(
        default=None,
        description=(
            "Dose exactly as written. MUST be null if the dose position contains "
            "the ILLEGIBLE marker, or if no dose is written at all. Never infer a "
            "typical or standard dose."
        ),
    )
    frequency: str | None = None
    dose_marked_illegible: bool = Field(
        default=False,
        description="True when the ILLEGIBLE marker sits where the dose should be.",
    )
    line_number: int = Field(default=0, description="The [Lnn] line this came from.")

    @field_validator("dose", "frequency", "name", mode="before")
    @classmethod
    def _scrub(cls, v):
        return _null_if_sentinel(v)


class ExtractedField(BaseModel):
    field: str = Field(description="One of the allowed field names supplied in the prompt.")
    value: str | None = Field(
        default=None,
        description="Verbatim or lightly normalised. Null if the content is illegible.",
    )
    marked_illegible: bool = False
    line_number: int = 0

    @field_validator("value", mode="before")
    @classmethod
    def _scrub(cls, v):
        return _null_if_sentinel(v)


class DocumentExtraction(BaseModel):
    """One document, read once."""

    document_kind: str = Field(
        description="referral_letter | medication_list | discharge_summary | intake_form | other"
    )
    fields: list[ExtractedField] = Field(default_factory=list)
    medications: list[ExtractedMedication] = Field(default_factory=list)
    notes: str | None = Field(
        default=None, description="Anything a human should know that does not fit a field."
    )
