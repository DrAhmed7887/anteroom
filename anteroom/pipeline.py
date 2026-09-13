"""Assembly: documents in, auditable IntakeRecord out.

The important line in this file is where confidence comes from. The model tells
us WHICH line holds the allergy list. The OCR gate tells us HOW WELL that line
was read. We take the semantics from the model and the certainty from the
measurement, and never the other way round.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .agents import interpret
from .extraction import DocumentExtraction
from .mapping import (
    is_real_medication,
    is_real_referral_question,
    load_not_a_medication,
    load_vague_referral_phrases,
    canonical_doc_kind,
    canonical_field,
    load_aliases,
    sanitise_dose,
    split_dose_frequency,
    strip_markers,
)
from .ocr import OcrDocument, OcrLine, read_document, state_for
from .readiness import CHANGE_LANGUAGE, audit, load_policy
from .schemas import (
    Confidence,
    DocumentMeta,
    ExtractedFact,
    IntakeRecord,
    Medication,
    ReadinessReport,
    SourceRef,
)

_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.UNREADABLE: 0}


def _line(doc: OcrDocument, n: int) -> OcrLine | None:
    return doc.lines[n - 1] if 1 <= n <= len(doc.lines) else None


def _source(doc: OcrDocument, line_no: int) -> SourceRef:
    ln = _line(doc, line_no)
    return SourceRef(
        document_id=doc.document_id,
        document_label=doc.label,
        location=f"line {line_no}" if ln else "whole document",
        bbox=ln.bbox if ln else None,
    )


def _confidence(doc: OcrDocument, line_no: int, marked_illegible: bool) -> Confidence:
    """Certainty is measured, not asserted."""
    if marked_illegible:
        return Confidence.UNREADABLE
    ln = _line(doc, line_no)
    if ln is None:
        return Confidence.LOW
    if ln.has_illegible:
        return Confidence.LOW
    return state_for(ln.confidence)


def facts_from(doc: OcrDocument, ex: DocumentExtraction, allowed: set[str],
               aliases: dict[str, str], vague: list[str] | None = None) -> dict[str, ExtractedFact]:
    out: dict[str, ExtractedFact] = {}
    vague = vague or []
    for f in ex.fields:
        canon = canonical_field(f.field, aliases, allowed)
        if canon is None:
            continue  # not something the policy asks about; notes keep the rest
        if canon == "referral_question" and not is_real_referral_question(f.value, vague):
            continue  # a courtesy is not a question
        value, had_marker = strip_markers(f.value)
        conf = _confidence(doc, f.line_number, f.marked_illegible or value is None)
        if had_marker and _RANK[conf] > _RANK[Confidence.LOW]:
            conf = Confidence.LOW
        out[canon] = ExtractedFact(
            field=canon,
            value=None if conf == Confidence.UNREADABLE else value,
            confidence=conf,
            source=_source(doc, f.line_number),
            note="OCR reported low confidence on part of this line." if had_marker else None,
        )
    return out


def medications_from(doc: OcrDocument, ex: DocumentExtraction,
                     stoplist: set[str] | None = None) -> list[Medication]:
    meds: list[Medication] = []
    stoplist = stoplist or set()
    for m in ex.medications:
        name, _ = strip_markers(m.name)
        if not is_real_medication(name, stoplist):
            continue
        dose_raw, freq = split_dose_frequency(m.dose, m.frequency)
        dose_raw, _ = strip_markers(dose_raw)
        dose, dose_note = sanitise_dose(dose_raw)
        freq, _ = strip_markers(freq)
        conf = _confidence(doc, m.line_number, m.dose_marked_illegible)
        note = None
        if m.dose_marked_illegible:
            note = "Dose position was unreadable in the source document."
        elif dose is None and dose_note:
            note = f"No dose recorded; document says: {dose_note!r}"
        meds.append(
            Medication(
                name=name, dose=dose, frequency=freq,
                confidence=conf, source=_source(doc, m.line_number), note=note,
            )
        )
    return meds


def document_signals(doc: OcrDocument) -> list[ExtractedFact]:
    """Scan the OCR transcript itself for statements that a medication was changed.

    This exists because the reconciliation finding -- the best thing this system
    does -- was previously reachable only if the interpreter happened to extract
    the right field. Across repeated runs it did so about half the time. A
    clinical finding must not depend on a model's discretion, so the signal is
    now read off the transcript, which is deterministic: the same image yields
    the same words every time.
    """
    out: list[ExtractedFact] = []
    for i, ln in enumerate(doc.lines, 1):
        text = ln.safe_text
        lowered = text.lower()
        if any(phrase in lowered for phrase in CHANGE_LANGUAGE):
            out.append(
                ExtractedFact(
                    field="_document_signal",
                    value=text,
                    confidence=state_for(ln.confidence),
                    source=_source(doc, i),
                    note="Read directly from the document text, not inferred.",
                )
            )
    return out


def _merge_medications(existing: list[Medication], incoming: list[Medication]) -> list[Medication]:
    """Same drug from two documents: keep the entry that actually has a dose,
    and prefer the better-read one. Never fabricate agreement."""
    by_name = {(m.name or "").lower(): m for m in existing}
    for new in incoming:
        key = (new.name or "").lower()
        old = by_name.get(key)
        if old is None:
            by_name[key] = new
            continue
        old_score = (old.dose is not None, _RANK[old.confidence])
        new_score = (new.dose is not None, _RANK[new.confidence])
        if new_score > old_score:
            new.note = new.note or old.note
            by_name[key] = new
    return list(by_name.values())


def build_record(
    patient_ref: str,
    appointment_at: datetime,
    visit_type: str,
    documents: list[tuple[str, str | Path, str]],
    model_id: str | None = None,
    textract_client=None,
) -> tuple[IntakeRecord, list[OcrDocument]]:
    """documents: list of (document_id, path, human label)."""
    policy = load_policy()
    allowed = set(policy["_global"].get("demographic_fields", [])) | {
        f
        for key, rules in policy.items()
        if not key.startswith("_") and isinstance(rules, dict)
        for tier in ("blocking", "important", "minor")
        for f in (rules.get(tier) or [])
    }
    aliases = load_aliases()
    stoplist = load_not_a_medication(policy)
    vague = load_vague_referral_phrases(policy)

    record = IntakeRecord(
        patient_ref=patient_ref, appointment_at=appointment_at, visit_type=visit_type
    )
    ocr_docs: list[OcrDocument] = []

    for doc_id, path, label in documents:
        doc = read_document(path, doc_id, label, client=textract_client)
        ex = interpret(doc, model_id=model_id)
        ocr_docs.append(doc)

        record.documents.append(
            DocumentMeta(
                document_id=doc_id,
                label=label,
                kind=canonical_doc_kind(ex.document_kind),
                capture_quality="degraded" if doc.illegible_count else "good",
                received_at=datetime.now(),
            )
        )

        doc_facts = facts_from(doc, ex, allowed, aliases, vague)
        record.all_facts.extend(doc_facts.values())
        record.all_facts.extend(document_signals(doc))

        for field, fact in doc_facts.items():
            current = record.facts.get(field)
            if current is None or _RANK[fact.confidence] > _RANK[current.confidence]:
                record.facts[field] = fact

        record.medications = _merge_medications(
            record.medications, medications_from(doc, ex, stoplist)
        )

    # A drug chart IS the current-medications field. Without this the policy
    # reports it missing while seven medications sit in the record.
    if record.medications and "current_medications" not in record.facts:
        named = [m for m in record.medications if m.name]
        best = max(named, key=lambda m: _RANK[m.confidence], default=None)
        if best is not None:
            record.facts["current_medications"] = ExtractedFact(
                field="current_medications",
                value=f"{len(named)} medications recorded: " + ", ".join(m.name for m in named),
                confidence=best.confidence,
                source=best.source,
            )

    return record, ocr_docs


def run(patient_ref, appointment_at, visit_type, documents, model_id=None, textract_client=None
        ) -> tuple[IntakeRecord, ReadinessReport, list[OcrDocument]]:
    record, docs = build_record(
        patient_ref, appointment_at, visit_type, documents, model_id, textract_client
    )
    return record, audit(record), docs
