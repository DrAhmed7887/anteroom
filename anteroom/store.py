"""Practice, users, appointments, and who is allowed to see what.

Authorisation here is real and enforced. Authentication is deliberately NOT:
there is no password, no session, no token. A production deployment would put
Amazon Cognito in front of this and map its claims onto `User`.

That split is the honest one for a system holding clinical documents. A
half-built login screen would look like security without being any. An
authorisation policy that is enforced on every read, covered by tests, and
written where a practice manager can read it, is the part that actually decides
whether reception can open a consultant's brief -- so that is the part that got
built.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .schemas import Gap, ReadinessReport, Role, Severity

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store"


class User(BaseModel):
    user_id: str
    name: str
    role: Role
    practice_id: str


class Practice(BaseModel):
    practice_id: str
    name: str
    address: str
    specialty: str


class Appointment(BaseModel):
    """The unit of work. Documents attach here, never float free.

    Gerhard's point, and it is the right one: a clinic pushing fifty documents
    through in a morning needs every one of them bound to a patient before
    anything else happens, or the pile is just a different pile.
    """

    appointment_id: str
    practice_id: str
    patient_ref: str = Field(description="Pseudonymous. The display name lives beside it.")
    patient_display: str
    appointment_at: datetime
    visit_type: str
    clinician: str
    document_ids: list[str] = Field(default_factory=list)


class AccessDenied(Exception):
    """Raised rather than returning empty, so a bug cannot look like 'no data'."""


class AuditEntry(BaseModel):
    at: datetime
    user_id: str
    action: str
    subject: str
    allowed: bool


# --------------------------------------------------------------- authorisation

def can_access(user: User, appointment: Appointment) -> bool:
    """Practice scoping. A user can only ever see their own practice's patients.

    This is the boundary that matters: not which tab someone opens, but whether
    another clinic's records are reachable at all.
    """
    return user.practice_id == appointment.practice_id


def require_access(user: User, appointment: Appointment, log: list[AuditEntry] | None = None) -> None:
    allowed = can_access(user, appointment)
    if log is not None:
        log.append(AuditEntry(at=datetime.now(), user_id=user.user_id,
                              action="open_appointment",
                              subject=appointment.appointment_id, allowed=allowed))
    if not allowed:
        raise AccessDenied(
            f"{user.name} ({user.practice_id}) may not open an appointment "
            f"belonging to {appointment.practice_id}."
        )


def visible_gaps(user: User, report: ReadinessReport) -> list[Gap]:
    """Role scoping. Each role sees the work that is theirs.

    An admin sees everything because somebody has to. A clinician additionally
    sees blocking items regardless of owner, because walking into a consultation
    unaware that an anticoagulant dose is unconfirmed is the failure this whole
    system exists to prevent.
    """
    if user.role == Role.ADMIN:
        return list(report.gaps)
    if user.role == Role.DOCTOR:
        own = report.gaps_for(Role.DOCTOR)
        blocking = [g for g in report.gaps if g.severity == Severity.BLOCKING]
        seen, out = set(), []
        for g in own + blocking:
            if g.field not in seen:
                seen.add(g.field)
                out.append(g)
        return out
    return report.gaps_for(user.role)


def can_view_clinical_brief(user: User) -> bool:
    """Reception coordinates appointments. They do not need the consultant's
    clinical summary, and least privilege says they should not have it."""
    return user.role in (Role.DOCTOR, Role.NURSE, Role.ADMIN)


# ---------------------------------------------------------------- persistence

def _p(name: str) -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    return STORE_DIR / name


def save_seed(practice: Practice, users: list[User], appointments: list[Appointment]) -> None:
    _p("practice.json").write_text(practice.model_dump_json(indent=2))
    _p("users.json").write_text(json.dumps([u.model_dump(mode="json") for u in users], indent=2))
    _p("appointments.json").write_text(
        json.dumps([a.model_dump(mode="json") for a in appointments], indent=2)
    )


def load_practice() -> Practice:
    return Practice.model_validate_json(_p("practice.json").read_text())


def load_users() -> list[User]:
    return [User.model_validate(u) for u in json.loads(_p("users.json").read_text())]


def load_appointments() -> list[Appointment]:
    return [Appointment.model_validate(a) for a in json.loads(_p("appointments.json").read_text())]


def load_appointment_detail(appointment_id: str) -> dict | None:
    path = _p(f"{appointment_id}.json")
    if not path.exists():
        return None
    return json.loads(path.read_text())
