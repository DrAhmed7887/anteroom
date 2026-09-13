"""Deterministic, model-free routes to finding a required field.

The interpreter is a language model, and language-model extraction recall is
not stable. The same referral letter produced readiness scores from 3 to 38
across identical runs, because an optional field was sometimes reported and
sometimes not. Anything a clinic acts on has to be steadier than that.

So every required field gets a second path that does not involve a model at
all. The generic one -- labelled sections -- does most of the work and requires
no per-specialty tuning, which matters because the documents that need to work
are the ones nobody has seen yet.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "config" / "field_evidence.yaml"

# "ALLERGIES: penicillin"  ·  "Reason for referral - chest pain"
# Bounded so a stray mid-sentence colon in prose cannot create a heading.
_HEADING = re.compile(r"^\s*([A-Za-z][A-Za-z /&'()-]{2,44})\s*[:–—-]\s+(.{3,})$")


def load_evidence(path: Path | None = None) -> dict:
    return yaml.safe_load((path or EVIDENCE_PATH).read_text()) or {}


def heading_match(line: str, aliases: dict[str, str], allowed: set[str]) -> tuple[str, str] | None:
    """Generic: does this line open with a label we recognise?

    This is the mechanism that generalises. A document we have never seen is
    far more likely to write "Allergies:" than to use our internal field names,
    and no keyword list has to be maintained for it to work.
    """
    m = _HEADING.match(line)
    if not m:
        return None
    label, value = m.group(1).strip().lower(), m.group(2).strip()
    direct = label.replace(" ", "_")
    if direct in allowed:
        return direct, value
    for alias, canonical in aliases.items():
        if (label == alias or label.startswith(alias)) and canonical in allowed:
            return canonical, value
    return None


def keyword_match(line: str, field: str, rules: dict) -> bool:
    """Supplementary: prose documents with no headings at all."""
    lowered = line.lower()
    all_of = rules.get("all_of") or []
    if all_of and not all(t in lowered for t in all_of):
        return False
    any_of = rules.get("any_of") or []
    if any_of and any(t in lowered for t in any_of):
        return True
    for combo in rules.get("or_all_of") or []:
        if all(t in lowered for t in combo):
            return True
    return False if (any_of or rules.get("or_all_of")) else bool(all_of)


def scan(lines: list[str], aliases: dict[str, str], allowed: set[str],
         evidence: dict | None = None) -> dict[str, tuple[int, str, str]]:
    """Return {field: (line_index_1_based, value, how_it_was_found)}.

    Headings win over keywords: an explicit label is stronger evidence than a
    word appearing somewhere in a sentence.
    """
    evidence = evidence if evidence is not None else load_evidence()
    found: dict[str, tuple[int, str, str]] = {}
    claimed: set[int] = set()

    for i, line in enumerate(lines, 1):
        hit = heading_match(line, aliases, allowed)
        if hit:
            field, value = hit
            claimed.add(i)
            if field not in found or found[field][2] == "keyword":
                found[field] = (i, value, "heading")

    for i, line in enumerate(lines, 1):
        # A line explicitly labelled for one field must not also be harvested
        # for another. "ALLERGIES: penicillin - widespread rash" contains the
        # word "rash", and without this it became the presenting complaint.
        if i in claimed:
            continue
        for field, rules in evidence.items():
            if field not in allowed or field in found:
                continue
            if keyword_match(line, field, rules):
                found[field] = (i, line.strip(), "keyword")
    return found
