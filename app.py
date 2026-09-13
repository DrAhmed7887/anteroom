"""Anteroom — the clinic console.

Three roles, one system, and a hard rule: nothing reaches a clinician as fact
unless a document was legible enough to support it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from anteroom.highlight import AMBER, RED, highlight, highlight_words
from anteroom.schemas import Gap, ReadinessReport, Role, Severity
from anteroom.store import (
    STORE_DIR,
    AccessDenied,
    Appointment,
    User,
    can_view_clinical_brief,
    load_appointments,
    load_practice,
    load_users,
    require_access,
    visible_gaps,
)

st.set_page_config(page_title="Anteroom", page_icon="🩺", layout="wide",
                   initial_sidebar_state="expanded")

CSS = """
<style>
  .stApp { background: #f6f8fb; }
  section[data-testid="stSidebar"] { background: #0f172a; }
  /* Scoped, not blanket: a global colour override here also repainted the
     status pills and button labels, making them invisible against their own
     backgrounds. */
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] h1,
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3,
  section[data-testid="stSidebar"] strong,
  section[data-testid="stSidebar"] .stCaption,
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  section[data-testid="stSidebar"] [data-testid="stExpander"] summary { color:#e2e8f0 !important; }
  section[data-testid="stSidebar"] code { color:#7dd3fc !important; background:#1e293b !important; }
  /* Patient buttons: legible slate cards, not white-on-white. */
  section[data-testid="stSidebar"] .stButton > button {
      background:#1e293b !important; color:#e2e8f0 !important; border:1px solid #334155 !important;
      text-align:left; font-weight:600; font-size:.88rem; border-radius:10px; }
  section[data-testid="stSidebar"] .stButton > button:hover {
      background:#334155 !important; border-color:#475569 !important; }
  section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
      background:#1e293b !important; border-color:#334155 !important; }
  section[data-testid="stSidebar"] div[data-baseweb="select"] * { color:#e2e8f0 !important; }
  /* Pills keep their own colours wherever they appear. */
  .p-red   { background:#fee2e2 !important; color:#991b1b !important; }
  .p-amber { background:#fef3c7 !important; color:#92400e !important; }
  .p-green { background:#d1fae5 !important; color:#065f46 !important; }
  .brand { font-size: 1.45rem; font-weight: 700; letter-spacing: -.02em; color:#fff !important; }
  .brand-sub { font-size:.76rem; color:#94a3b8 !important; margin-top:-4px; letter-spacing:.04em;
               text-transform:uppercase; }
  .card { background:#fff; border:1px solid #e6eaf2; border-radius:14px; padding:18px 20px;
          margin-bottom:14px; box-shadow:0 1px 3px rgba(15,23,42,.05); }
  .pill { display:inline-block; padding:4px 12px; border-radius:999px; font-size:.72rem;
          font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
  .p-red   { background:#fee2e2; color:#991b1b; }
  .p-amber { background:#fef3c7; color:#92400e; }
  .p-green { background:#d1fae5; color:#065f46; }
  .score { font-size:2.6rem; font-weight:800; line-height:1; letter-spacing:-.03em; }
  .muted { color:#64748b; font-size:.84rem; }
  .gap { border-left:4px solid #cbd5e1; padding:12px 16px; margin-bottom:10px;
         background:#fff; border-radius:0 10px 10px 0; border-top:1px solid #eef1f6;
         border-right:1px solid #eef1f6; border-bottom:1px solid #eef1f6; }
  .g-block { border-left-color:#dc2626; }
  .g-imp   { border-left-color:#f59e0b; }
  .g-min   { border-left-color:#94a3b8; }
  .gap-title { font-weight:650; font-size:.95rem; color:#0f172a; }
  .script { background:#0f172a; color:#e2e8f0; padding:14px 16px; border-radius:10px;
            font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem;
            line-height:1.55; margin-top:8px; }
  .brief-h { font-size:1.3rem; font-weight:700; color:#0f172a; letter-spacing:-.02em; }
  .med { font-family:ui-monospace,Menlo,monospace; font-size:.86rem; padding:7px 12px;
         border-radius:8px; background:#f8fafc; margin-bottom:5px; border:1px solid #eef1f6; }
  .med-missing { background:#fef2f2; border-color:#fecaca; color:#991b1b; font-weight:600; }
  .conf { font-family:ui-monospace,Menlo,monospace; font-size:.78rem; }
  h1,h2,h3 { color:#0f172a !important; letter-spacing:-.02em; }
  .stTabs [data-baseweb="tab"] { font-weight:600; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

STATUS_STYLE = {
    "at_risk": ("p-red", "#dc2626", "AT RISK"),
    "needs_action": ("p-amber", "#d97706", "NEEDS ACTION"),
    "ready": ("p-green", "#059669", "READY"),
}
SEV_CLASS = {Severity.BLOCKING: "g-block", Severity.IMPORTANT: "g-imp", Severity.MINOR: "g-min"}


# ------------------------------------------------------------------ data load

@st.cache_data(show_spinner=False)
def load_case(appointment_id: str) -> dict | None:
    p = STORE_DIR / f"{appointment_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def get_report(case: dict) -> ReadinessReport:
    return ReadinessReport.model_validate(case["report"])


if "audit" not in st.session_state:
    st.session_state.audit = []

try:
    practice, users, appointments = load_practice(), load_users(), load_appointments()
except FileNotFoundError:
    st.error("No demo data. Run `python scripts/seed_demo.py` first.")
    st.stop()


# ---------------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown(f'<div class="brand">🩺 Anteroom</div>'
                f'<div class="brand-sub">{practice.name}</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("**Signed in as**")
    labels = {f"{u.name} · {u.role.value}" + ("  ⚠ other practice" if u.practice_id != practice.practice_id else ""): u
              for u in users}
    choice = st.selectbox("user", list(labels), label_visibility="collapsed")
    me: User = labels[choice]
    st.caption(f"Practice: `{me.practice_id}`  ·  Role: `{me.role.value}`")

    st.markdown("---")
    st.markdown("**Tomorrow's list**")
    for a in appointments:
        case = load_case(a.appointment_id)
        if not case:
            continue
        rep = get_report(case)
        cls, colour, label = STATUS_STYLE[rep.status.value]
        if st.button(f"{a.appointment_at:%H:%M}  {a.patient_display}",
                     key=f"b-{a.appointment_id}", use_container_width=True):
            st.session_state.selected = a.appointment_id
        st.markdown(
            f'<div style="margin:-8px 0 12px 4px"><span class="pill {cls}">{label}</span>'
            f'<span class="muted" style="margin-left:8px">{rep.score}/100</span></div>',
            unsafe_allow_html=True)

    st.markdown("---")
    with st.expander("Access log", expanded=False):
        if not st.session_state.audit:
            st.caption("No access attempts yet.")
        for e in reversed(st.session_state.audit[-12:]):
            mark = "✅" if e.allowed else "⛔"
            st.markdown(f'<div class="conf">{mark} {e.at:%H:%M:%S} · {e.user_id} · '
                        f'{e.subject}</div>', unsafe_allow_html=True)

    st.caption("All patient data is synthetic. Authorisation is enforced; "
               "authentication is stubbed for the demo.")


# ------------------------------------------------------------------- main pane

selected_id = st.session_state.get("selected", appointments[0].appointment_id)
appointment: Appointment = next(a for a in appointments if a.appointment_id == selected_id)

try:
    require_access(me, appointment, st.session_state.audit)
except AccessDenied as exc:
    st.markdown(f'<div class="card" style="border-color:#fecaca;background:#fff5f5">'
                f'<span class="pill p-red">access denied</span>'
                f'<h3 style="margin:10px 0 6px">This record belongs to another practice</h3>'
                f'<div class="muted">{exc}</div>'
                f'<div class="muted" style="margin-top:10px">The request was refused and logged. '
                f'Anteroom raises on a cross-practice read rather than returning an empty '
                f'result, because silence is indistinguishable from "this patient has no '
                f'documents".</div></div>', unsafe_allow_html=True)
    st.stop()

case = load_case(appointment.appointment_id)
report = get_report(case)
brief = case["brief"]
record = case["record"]
docs = {d["document_id"]: d for d in case["documents"]}
cls, colour, label = STATUS_STYLE[report.status.value]

c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f"### {appointment.patient_display}")
    st.markdown(
        f'<div class="muted">{appointment.visit_type.replace("_"," ")} · '
        f'{appointment.appointment_at:%A %d %B, %H:%M} · {appointment.clinician} · '
        f'ref <code>{appointment.patient_ref}</code></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div style="text-align:right">'
                f'<span class="pill {cls}">{label}</span>'
                f'<div class="score" style="color:{colour}">{report.score}<span '
                f'style="font-size:1rem;color:#94a3b8">/100</span></div>'
                f'<div class="muted">{len(report.gaps)} gaps · '
                f'{len(report.blocking_gaps)} blocking</div></div>', unsafe_allow_html=True)

st.markdown("")

mine = visible_gaps(me, report)
tab_names = ["My queue", "Source documents", "Confidence gate"]
if can_view_clinical_brief(me):
    tab_names.insert(1, "Clinician brief")
tabs = st.tabs(tab_names)
T = dict(zip(tab_names, tabs))


def render_gap(g: Gap) -> None:
    st.markdown(
        f'<div class="gap {SEV_CLASS[g.severity]}">'
        f'<div class="gap-title">{g.field.split(":",1)[-1].replace("_"," ")}'
        f'<span class="muted" style="margin-left:10px">{g.severity.value} · {g.reason}</span></div>'
        f'<div class="muted" style="margin-top:6px;color:#334155">{g.action}</div>'
        + (f'<div class="script">☎ {g.call_script}</div>' if g.call_script else "")
        + (f'<div class="muted" style="margin-top:8px">Source: {g.source.document_label}'
           f' · {g.source.location}</div>' if g.source else "")
        + '</div>', unsafe_allow_html=True)


with T["My queue"]:
    if not mine:
        st.markdown('<div class="card"><span class="pill p-green">nothing to do</span>'
                    '<div style="margin-top:10px">No outstanding items for this role. '
                    'The appointment can go ahead.</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="muted" style="margin-bottom:12px">'
                    f'{len(mine)} item(s) assigned to <b>{me.role.value}</b>. '
                    f'Other roles see their own work, not this.</div>', unsafe_allow_html=True)
        for g in mine:
            render_gap(g)


if "Clinician brief" in T:
    with T["Clinician brief"]:
        n = brief["narrative"]
        st.markdown(f'<div class="card"><div class="brief-h">{n["headline"]}</div>'
                    + "".join(f'<div class="muted" style="margin-top:6px;color:#334155">· {b}</div>'
                              for b in n["background"])
                    + '</div>', unsafe_allow_html=True)

        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Medications**")
            for m in brief["medications"]:
                missing = "NOT DOCUMENTED" in m
                st.markdown(f'<div class="med {"med-missing" if missing else ""}">'
                            f'{"⚠ " if missing else ""}{m}</div>', unsafe_allow_html=True)
        with cB:
            st.markdown("**Not documented**")
            for u in brief["not_documented"]:
                st.markdown(f'<div class="med">{u}</div>', unsafe_allow_html=True)

        if brief["before_you_start"]:
            st.markdown("**Before you start**")
            for x in brief["before_you_start"]:
                st.markdown(f'<div class="gap g-block"><div class="muted" '
                            f'style="color:#334155">{x}</div></div>', unsafe_allow_html=True)
        st.caption("Every statement here derives from a document that was legible enough to "
                   "support it. Anteroom does not diagnose, prescribe, or assess urgency.")


with T["Source documents"]:
    doc_id = st.selectbox("Document", list(docs),
                          format_func=lambda k: docs[k]["label"])
    doc = docs[doc_id]
    left, right = st.columns([3, 2])
    with right:
        st.markdown(f'<div class="card"><b>{doc["label"]}</b>'
                    f'<div class="muted" style="margin-top:6px">'
                    f'{len(doc["lines"])} lines · {doc["illegible_count"]} illegible token(s)'
                    f'</div></div>', unsafe_allow_html=True)
        st.markdown("**Facts drawn from this document**")
        picked = None
        for key, f in record["facts"].items():
            if f["source"]["document_id"] != doc_id:
                continue
            if st.button(f"{key.replace('_',' ')}", key=f"f-{doc_id}-{key}",
                         use_container_width=True):
                st.session_state[f"sel-{doc_id}"] = key
            st.markdown(f'<div class="muted" style="margin:-6px 0 10px 4px">'
                        f'{(f["value"] or "—")[:70]} · <span class="conf">'
                        f'{f["confidence"]}</span></div>', unsafe_allow_html=True)
        picked = st.session_state.get(f"sel-{doc_id}")
    with left:
        boxes, colour = [], AMBER
        if picked and picked in record["facts"]:
            bb = record["facts"][picked]["source"].get("bbox")
            if bb:
                boxes = [bb]
                colour = RED if record["facts"][picked]["confidence"] == "unreadable" else AMBER
        st.image(highlight(doc["path"], boxes, colour=colour),
                 caption=f"{doc['label']}" + (f" — highlighting “{picked.replace('_',' ')}”"
                                              if picked else " — select a fact to locate it"),
                 use_container_width=True)


with T["Confidence gate"]:
    st.markdown('<div class="card">Amazon Textract returns a confidence score for every word. '
                'Anything below the floor has its text <b>deleted</b> before a language model '
                'sees the page, so the model cannot infer a value from something it was never '
                'shown. Green survived. Red was removed.</div>', unsafe_allow_html=True)
    # Default to the document that actually exercised the gate. Opening on a
    # clean page that reads "0 deleted" buries the point.
    order = sorted(docs, key=lambda k: -docs[k]["illegible_count"])
    gate_doc = st.selectbox("Document ", order, format_func=lambda k: docs[k]["label"],
                            key="gatedoc")
    d = docs[gate_doc]
    words = [w for ln in d["lines"] for w in ln["words"]]
    low = [w for w in words if w["state"] in ("low", "unreadable")]
    gl, gr = st.columns([3, 2])
    with gl:
        st.image(highlight_words(d["path"], words), use_container_width=True)
    with gr:
        st.markdown(f"**{len(words)} words · {len([w for w in words if w['state']=='unreadable'])} "
                    f"deleted**")
        for w in sorted(low, key=lambda x: x["confidence"])[:14]:
            c = "#dc2626" if w["state"] == "unreadable" else "#d97706"
            shown = "⟪deleted⟫" if w["state"] == "unreadable" else w["text"]
            st.markdown(f'<div class="conf" style="padding:5px 0;border-bottom:1px solid #eef1f6">'
                        f'<span style="color:{c};font-weight:700">{w["confidence"]:.1f}%</span>'
                        f'&nbsp;&nbsp;{shown}</div>', unsafe_allow_html=True)
        if not low:
            st.markdown('<div class="muted">Every word on this document passed the gate.</div>',
                        unsafe_allow_html=True)
