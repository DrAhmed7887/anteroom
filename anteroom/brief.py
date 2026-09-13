"""The clinician's pre-visit brief.

Split deliberately down the middle:

  the model writes  -- the narrative sentences, from facts that passed the gate
  code renders      -- every medication line, every dose, every unknown

A language model writing "she takes apixaban 5mg twice daily" in fluent prose is
the exact failure this system exists to prevent, and no prompt makes that
impossible. So the model is never given the opportunity: it receives a list of
usable facts with the doses already stripped out, and the medication block is
assembled by code that cannot invent a number it was not given.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from strands import Agent

from .agents import build_model
from .schemas import Confidence, IntakeRecord, ReadinessReport, Severity

BRIEF_PROMPT = """\
You write the two-sentence orientation a consultant reads in the corridor before
calling a patient in. You are given only facts that were legibly read from that
patient's documents.

RULES
1. Use only what you are given. Never add a clinical detail, a number, a dose, a
   date, or a diagnosis that is not in the supplied facts.
2. Never state or imply a medication dose. Doses are rendered separately by the
   system and are not your responsibility.
3. Do not diagnose, do not suggest management, do not assess urgency. You are
   orienting a clinician, not advising one.
4. Plain clinical register. No hedging, no filler, no "it is important to note".
5. If a fact is absent, say nothing about it. The system lists unknowns itself.
"""


class BriefNarrative(BaseModel):
    """The only part a model is allowed to write."""

    headline: str = Field(
        description="One line, under 18 words: age and sex if supplied, then the "
        "single reason this appointment exists. If age or sex are absent, simply "
        "omit them -- never write 'sex unknown' or 'adult'."
    )
    background: list[str] = Field(
        default_factory=list,
        description="Up to four short phrases of relevant history. No doses, no numbers "
        "you were not given.",
    )


class DoctorBrief(BaseModel):
    """What actually reaches the clinician. Only `narrative` came from a model."""

    patient_ref: str
    appointment: str
    narrative: BriefNarrative
    medications: list[str] = Field(default_factory=list)
    not_documented: list[str] = Field(default_factory=list)
    before_you_start: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


def _usable_facts(record: IntakeRecord) -> dict[str, str]:
    """Only facts that survived the confidence gate may inform the narrative."""
    return {k: f.value for k, f in record.facts.items() if f.is_usable and f.value}


def render_medications(record: IntakeRecord) -> list[str]:
    """Deterministic. A dose appears here only if a dose was read from a document.

    'Apixaban - DOSE NOT DOCUMENTED' is the single most important line this
    system produces, and it is produced by string concatenation, not inference.
    """
    lines: list[str] = []
    for m in sorted(record.medications, key=lambda x: (x.name or "").lower()):
        if not m.name:
            continue
        if m.confidence == Confidence.UNREADABLE or m.dose is None:
            detail = "DOSE NOT DOCUMENTED"
            if m.note and "unreadable" in m.note.lower():
                detail += " (illegible in source)"
        else:
            detail = m.dose
        freq = f", {m.frequency}" if m.frequency else ""
        lines.append(f"{m.name} — {detail}{freq}")
    return lines


def render_unknowns(report: ReadinessReport) -> list[str]:
    """What the clinic does not know, stated plainly rather than omitted."""
    out: list[str] = []
    for g in report.gaps:
        if g.severity == Severity.MINOR:
            continue
        label = g.field.split(":", 1)[-1].replace("_", " ")
        if g.reason == "unreadable":
            out.append(f"{label} — present in a document but not legible")
        elif g.reason == "conflicting":
            out.append(f"{label} — documents disagree or a change is unresolved")
        else:
            out.append(f"{label} — not documented")
    return out


def compose(record: IntakeRecord, report: ReadinessReport, model_id: str | None = None
            ) -> DoctorBrief:
    facts = _usable_facts(record)
    agent = Agent(
        model=build_model(model_id),
        system_prompt=BRIEF_PROMPT,
        callback_handler=None,
        name="brief_composer",
        description="Writes the consultant's two-line orientation from gated facts.",
    )
    payload = "\n".join(f"- {k.replace('_',' ')}: {v}" for k, v in facts.items())
    result = agent(
        f"Facts legibly read from this patient's documents:\n{payload}\n\n"
        "Write the headline and background.",
        structured_output_model=BriefNarrative,
    )

    blocking = [
        g.action for g in report.gaps if g.severity == Severity.BLOCKING
    ]
    sources = sorted({f.source.document_label for f in record.facts.values()})

    return DoctorBrief(
        patient_ref=record.patient_ref,
        appointment=f"{record.appointment_at:%a %d %b, %H:%M}",
        narrative=result.structured_output,
        medications=render_medications(record),
        not_documented=render_unknowns(report),
        before_you_start=blocking,
        sources=sources,
    )
