"""Deterministic normalisation between what documents say and what policy asks.

Everything here runs after the model and before the auditor. None of it is
inference: it is a lookup table a clinician can read, argue with, and correct
without touching a prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ALIAS_PATH = Path(__file__).resolve().parent.parent / "config" / "field_aliases.yaml"

LOW_CONF_MARKER = "⟨?⟩"
DOC_KINDS = {"referral_letter", "medication_list", "discharge_summary", "intake_form", "other"}

_FREQUENCY_WORDS = re.compile(
    r"^(when needed|as needed|prn|once daily|twice a day|twice daily|at night|"
    r"morning|nocte|od|bd|tds|qds|as directed|daily|weekly)$",
    re.I,
)


def load_aliases(path: Path | None = None) -> dict[str, str]:
    """Flatten the synonym file into alias -> canonical, longest alias first so
    'renal function' wins over 'renal'."""
    raw = yaml.safe_load((path or ALIAS_PATH).read_text())
    pairs: list[tuple[str, str]] = []
    for canonical, aliases in raw.items():
        pairs.append((canonical.lower(), canonical))
        for a in aliases:
            pairs.append((a.lower(), canonical))
    return dict(sorted(pairs, key=lambda kv: -len(kv[0])))


def canonical_field(name: str, aliases: dict[str, str], allowed: set[str]) -> str | None:
    """Resolve a model-supplied field name to a policy field name, or None."""
    if not name:
        return None
    lowered = name.strip().lower().replace("_", " ")
    if lowered.replace(" ", "_") in allowed:
        return lowered.replace(" ", "_")
    for alias, canon in aliases.items():
        if alias in lowered and canon in allowed:
            return canon
    return None


def strip_markers(value: str | None) -> tuple[str | None, bool]:
    """Remove OCR confidence markers from a value, reporting whether any were
    present. The marker is a signal for the pipeline, not content for a human."""
    if value is None:
        return None, False
    had = LOW_CONF_MARKER in value
    cleaned = value.replace(LOW_CONF_MARKER, "").strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return (cleaned or None), had


def split_dose_frequency(dose: str | None, frequency: str | None) -> tuple[str | None, str | None]:
    """Models routinely put 'when needed' in the dose field. A frequency is not
    a dose, and treating it as one would let a drug with no recorded dose look
    fully documented."""
    if dose and _FREQUENCY_WORDS.match(dose.strip()):
        return None, frequency or dose.strip()
    return dose, frequency


def canonical_doc_kind(kind: str | None) -> str:
    if not kind:
        return "other"
    k = kind.strip().lower().replace(" ", "_").replace("-", "_")
    if k in DOC_KINDS:
        return k
    for candidate in DOC_KINDS:
        if candidate.replace("_", "") in k.replace("_", ""):
            return candidate
    if "referral" in k:
        return "referral_letter"
    if "medication" in k or "drug" in k:
        return "medication_list"
    if "discharge" in k:
        return "discharge_summary"
    return "other"


# A dose is a quantity with a unit, or an explicit "as directed". Prose is not a
# dose. The discharge summary in our corpus produced dose="Dose reduced on
# discharge" -- true, informative, and not a dose. Accepting it would have made
# a drug with no recorded dose look fully documented.
_DOSE_SHAPE = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:"
    r"mg/kg|mcg/kg|mg|mcg|µg|ug|g|kg|ml|l|"
    r"micrograms?|milligrams?|millilitres?|milliliters?|grams?|"
    r"units?|iu|international units?|puffs?|drops?|tablets?|caps?|capsules?|sprays?|patch(?:es)?|"
    r"mmol|%"
    r")\b"
    r"|\d+\s*/\s*\d+\s*(?:mg|mcg|micrograms?)\b"
    r"|as directed|prn only)",
    re.I,
)


def load_not_a_medication(policy: dict) -> set[str]:
    return {x.lower() for x in policy["_global"].get("not_a_medication", [])}


def is_real_medication(name: str | None, stoplist: set[str]) -> bool:
    """A drug class is not a drug. Deterministic, auditable, in config."""
    if not name:
        return False
    return name.strip().lower() not in stoplist


def load_vague_referral_phrases(policy: dict) -> list[str]:
    return [p.lower() for p in policy["_global"].get("vague_referral_phrases", [])]


def is_real_referral_question(value: str | None, vague: list[str]) -> bool:
    """A referral question names what is being asked. A courtesy does not.

    Rejecting these is the difference between reporting "referral question
    present" and reporting the truth, which is that the consultant still does
    not know why this patient is coming.
    """
    if not value or not value.strip():
        return False
    stripped = value.strip().lower().rstrip(".")
    if len(stripped) < 8:
        # Shorter than any real clinical question. "?" and "n/a" were passing.
        return False
    for phrase in vague:
        if phrase in stripped and len(stripped) <= len(phrase) + 25:
            return False
    return True


def sanitise_dose(dose: str | None) -> tuple[str | None, str | None]:
    """Return (dose, note). Anything that is not dose-shaped becomes a note."""
    if dose is None:
        return None, None
    m = _DOSE_SHAPE.search(dose)
    if m:
        return m.group(0).strip(), (dose.strip() if len(dose.strip()) > len(m.group(0)) + 3 else None)
    return None, dose.strip() or None
