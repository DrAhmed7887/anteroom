"""Authorisation is enforced, and these tests are the proof.

Authentication is stubbed for the demo; authorisation is not. The boundary that
matters is not which tab a user opens -- it is whether another practice's
clinical records are reachable at all.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from anteroom.readiness import audit
from anteroom.schemas import (
    Confidence,
    IntakeRecord,
    Medication,
    ReadinessReport,
    ReadinessStatus,
    Role,
    Severity,
    SourceRef,
)
from anteroom.store import (
    AccessDenied,
    Appointment,
    User,
    can_access,
    can_view_clinical_brief,
    require_access,
    visible_gaps,
)

SRC = SourceRef(document_id="d1", document_label="Medication list", location="line 3")


def appt(practice_id="riverside", appointment_id="a1"):
    return Appointment(
        appointment_id=appointment_id, practice_id=practice_id, patient_ref="SYN-1",
        patient_display="M. Ruiz", appointment_at=datetime(2026, 9, 14, 14, 30),
        visit_type="cardiology_new_consult", clinician="Dr Hale",
    )


def user(role=Role.RECEPTION, practice_id="riverside", uid="u1"):
    return User(user_id=uid, name="Test User", role=role, practice_id=practice_id)


@pytest.fixture
def report() -> ReadinessReport:
    rec = IntakeRecord(
        patient_ref="SYN-1", appointment_at=datetime(2026, 9, 14, 14, 30),
        visit_type="cardiology_new_consult",
        medications=[
            Medication(name="Apixaban", dose=None, confidence=Confidence.UNREADABLE, source=SRC),
            Medication(name="Paracetamol", dose=None, confidence=Confidence.HIGH, source=SRC),
        ],
    )
    return audit(rec)


# ------------------------------------------------------------ practice scoping

def test_a_user_cannot_open_another_practices_appointment():
    outsider = user(practice_id="other-clinic")
    assert can_access(outsider, appt(practice_id="riverside")) is False


def test_cross_practice_access_raises_rather_than_returning_empty():
    """A silent empty result is indistinguishable from 'this patient has no
    documents', which is exactly the confusion that hides a security bug."""
    with pytest.raises(AccessDenied):
        require_access(user(practice_id="other-clinic"), appt())


def test_own_practice_access_is_allowed():
    require_access(user(practice_id="riverside"), appt(practice_id="riverside"))


def test_every_access_decision_is_audited():
    log = []
    with pytest.raises(AccessDenied):
        require_access(user(practice_id="other"), appt(), log)
    require_access(user(practice_id="riverside"), appt(), log)
    assert [e.allowed for e in log] == [False, True]
    assert all(e.action == "open_appointment" for e in log)


# ---------------------------------------------------------------- role scoping

def test_reception_cannot_view_the_clinical_brief():
    assert can_view_clinical_brief(user(Role.RECEPTION)) is False
    assert can_view_clinical_brief(user(Role.NURSE)) is True
    assert can_view_clinical_brief(user(Role.DOCTOR)) is True


def test_reception_sees_only_reception_work(report):
    gaps = visible_gaps(user(Role.RECEPTION), report)
    assert gaps, "reception queue should not be empty for this patient"
    assert all(g.owner == Role.RECEPTION for g in gaps)


def test_nurse_does_not_see_receptions_queue(report):
    gaps = visible_gaps(user(Role.NURSE), report)
    assert all(g.owner == Role.NURSE for g in gaps)


def test_clinician_always_sees_blocking_items_whoever_owns_them(report):
    """Walking into a consultation unaware that an anticoagulant dose is
    unconfirmed is the failure this system exists to prevent."""
    gaps = visible_gaps(user(Role.DOCTOR), report)
    blocking = [g for g in report.gaps if g.severity == Severity.BLOCKING]
    assert blocking, "fixture should produce at least one blocking gap"
    for b in blocking:
        assert any(g.field == b.field for g in gaps)


def test_clinician_view_has_no_duplicates(report):
    gaps = visible_gaps(user(Role.DOCTOR), report)
    assert len({g.field for g in gaps}) == len(gaps)
