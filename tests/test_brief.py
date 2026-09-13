"""The brief is the last place a fabricated dose could reach a clinician.

Everything here tests the deterministic half -- the half that renders doses and
unknowns. No model runs in these tests, which is the point: the guarantee must
hold without one.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from anteroom.brief import render_medications, render_unknowns
from anteroom.readiness import audit
from anteroom.schemas import Confidence, IntakeRecord, Medication, SourceRef

SRC = SourceRef(document_id="d1", document_label="Medication list", location="line 3")


def med(name, dose=None, conf=Confidence.HIGH, note=None, freq=None):
    return Medication(name=name, dose=dose, frequency=freq, confidence=conf, source=SRC, note=note)


@pytest.fixture
def record():
    return IntakeRecord(
        patient_ref="SYN-TEST",
        appointment_at=datetime(2026, 9, 14, 14, 30),
        visit_type="cardiology_new_consult",
        medications=[
            med("Ramipril", "5mg", freq="morning"),
            med("Apixaban", None, Confidence.UNREADABLE,
                note="Dose position was unreadable in the source document."),
            med("Paracetamol", None),
        ],
    )


def test_unreadable_dose_is_stated_not_omitted(record):
    """Silence would be worse than the gap. The clinician must see that the
    dose is unknown, not simply fail to see a dose."""
    lines = render_medications(record)
    apix = next(l for l in lines if l.startswith("Apixaban"))
    assert "DOSE NOT DOCUMENTED" in apix
    assert "illegible in source" in apix


def test_no_dose_is_ever_invented(record):
    """The rendered block may only contain doses that were read from a document."""
    blob = " ".join(render_medications(record)).lower()
    for invented in ("2.5mg", "5 mg twice", "10mg", "apixaban 5mg", "apixaban 2.5"):
        assert invented not in blob


def test_a_read_dose_survives_verbatim(record):
    assert "Ramipril — 5mg, morning" in render_medications(record)


def test_medication_without_a_dose_still_appears(record):
    """An as-needed drug with no dose is not hidden; it is shown as undocumented."""
    assert any(l.startswith("Paracetamol") and "DOSE NOT DOCUMENTED" in l
               for l in render_medications(record))


def test_unknowns_distinguish_illegible_from_absent(record):
    """'We could not read it' and 'it was never there' are different problems
    and route to different people."""
    report = audit(record)
    unknowns = render_unknowns(report)
    joined = " ".join(unknowns)
    assert "not documented" in joined
    assert any("not legible" in u or "unresolved" in u for u in unknowns)


def test_minor_gaps_stay_out_of_the_clinician_view(record):
    """A consultant reading a corridor brief should not be shown a missing
    family history. Minor gaps belong to reception."""
    report = audit(record)
    minor_fields = {g.field for g in report.gaps if g.severity.value == "minor"}
    rendered = " ".join(render_unknowns(report))
    for f in minor_fields:
        label = f.split(":", 1)[-1].replace("_", " ")
        assert label not in rendered


def test_no_regulated_clinical_process_is_claimed(record):
    """Anteroom flags an incomplete intake packet. It does not perform medicines
    reconciliation, which is a regulated process carried out by pharmacists."""
    report = audit(record)
    surface = " ".join([g.action for g in report.gaps] + render_unknowns(report)).lower()
    assert "medicines reconciliation" not in surface
    assert "reconcile" not in surface
