# Anteroom — MVP Product Document (PD)

**Product:** Anteroom — Ambient Clinical Intake Coordinator  
**Hackathon:** Agents for Humans (AWS × Strands Agents SDK)  
**Track:** Professional Agents  
**Authors:** Dr. Ahmed Zayed (MBBCh, MSc Applied Health Informatics candidate) & Gerhard  
**Target Submission:** Monday 14 September 2026, 20:00 CEST (Deadline: 15 Sep 02:00 CEST / 00:00 UTC)  
**License:** MIT (Public Open Source)  
**Working Repository:** `~/Downloads/Agents for Humans Hackathon/anteroom/`

---

## 1. Executive Summary & Value Proposition

### 1.1 One-Line Pitch
**Anteroom checks tomorrow’s clinic list tonight, verifies whether scheduled appointments can actually proceed, and hands reception the exact three calls to make in the morning.**

### 1.2 The Problem: The Burned Appointment Slot
In specialist outpatient clinics, physicians do not lose time simply because records are long—they lose entire consultations because intake is fragmented and illegible:
* A patient arrives for a 30-minute cardiology consultation.
* The photographed referral letter gives history but omits the referral question.
* The handwritten medication list has a smudged blood-thinner dose.
* The hospital discharge screen photo has glare over renal lab results.
* **The Outcome:** The physician cannot safely make a management decision. A 30-minute slot becomes an administrative re-booking, revenue is burned, clinic capacity is lost, and the patient waits another 4 weeks.

### 1.3 The Solution
Anteroom is an ambient pre-visit intake coordinator built with the **Strands Agents SDK** and deployed via **Amazon Bedrock AgentCore**. It ingests messy real-world intake artifacts (angled phone photos, handwritten notes, photographed computer screens), deterministically audits readiness against clinic policy, and routes actionable tasks to the right person before the patient ever arrives.

```
Messy Intake Photos              Deterministic Policy              Role-Specific Action
 (Paper, Screen, Note)         (visit_requirements.yaml)             (Before Visit)
       │                                 │                                 │
       ▼                                 ▼                                 ▼
┌──────────────┐                 ┌───────────────┐                 ┌───────────────┐
│   Textract   │ ──⟪ILLEGIBLE⟫──►│    Strands    │ ───────────────►│ Receptionist  │ (Phone scripts)
│  Confidence  │                 │ Orchestrator  │                 ├───────────────┤
│     Gate     │                 │   + Auditor   │ ───────────────►│ Nurse Queue   │ (Clinical gap)
└──────────────┘                 └───────────────┘                 ├───────────────┤
                                                                   │ Doctor Brief  │ (30s brief)
                                                                   └───────────────┘
```

### 1.4 Non-Negotiable Product Boundary
* **Anteroom does NOT diagnose.**
* **Anteroom does NOT prescribe or recommend treatments.**
* **Anteroom does NOT perform emergency clinical triage.**
* **Anteroom is strictly an assistive pre-visit completeness and audit coordinator.**

---

## 2. Technical Stack: Strands Agents SDK & Amazon Bedrock AgentCore

The system is deliberately engineered to showcase deep, authentic implementation of the AWS agent ecosystem:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       Amazon Bedrock AgentCore Runtime                          │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      Strands Agents SDK (Python 1.55+)                  │   │
│   │                                                                         │   │
│   │   ┌─────────────────────────────────────────────────────────────────┐   │   │
│   │   │                Intake Coordinator (Supervisor Agent)            │   │   │
│   │   └──────┬──────────────────────────┬───────────────────────┬───────┘   │   │
│   │          │                          │                       │           │   │
│   │          ▼                          ▼                       ▼           │   │
│   │   ┌──────────────┐           ┌──────────────┐        ┌──────────────┐   │   │
│   │   │   Document   │           │  Readiness   │        │ Pre-Visit    │   │   │
│   │   │ Interpreter  │           │   Auditor    │        │ Brief        │   │   │
│   │   │    Agent     │           │    Tool      │        │ Composer     │   │   │
│   │   └──────────────┘           └──────────────┘        └──────────────┘   │   │
│   │          ▲                          ▲                       ▲           │   │
│   │          │                          │                       │           │   │
│   │   ┌──────────────┐           ┌──────────────┐               │           │   │
│   │   │   Textract   │           │    YAML      │               │           │   │
│   │   │  Confidence  │           │   Policy     │               │           │   │
│   │   │     Gate     │           │   Engine     │               │           │   │
│   │   └──────────────┘           └──────────────┘               │           │   │
│   │                                                             │           │   │
│   └─────────────────────────────────────────────────────────────┼───────────┘   │
│                                                                 │               │
│   ┌─────────────────────────────────────────────────────────────▼───────────┐   │
│   │                 AgentCore Observability & OpenTelemetry Trace           │   │
│   │   - Step-by-step reasoning trace                                        │   │
│   │   - Bounding-box visual provenance logging                              │   │
│   │   - Human-in-the-loop review state transition                           │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Strands Agents SDK Implementation Details

1. **Two agents, deliberately narrow — no supervisor.**
   - `anteroom/agents.py` — **Document Interpreter**: turns a gated OCR transcript into
     structured fields. Reports semantics only. Never reports certainty, never rates
     clinical risk, never sees an image.
   - `anteroom/brief.py` — **Brief Composer**: writes two sentences of orientation for
     the consultant from facts that already passed the confidence gate.
   - Both use Strands structured output against strict Pydantic contracts.

   There is deliberately **no orchestrator agent and no model-driven state machine.**
   Sequencing an intake packet is not a judgement call, so it is ordinary code in
   `anteroom/pipeline.py`. Every safety-critical decision sits outside the agents:

   | decision | where | model involved |
   |---|---|---|
   | delete an unreadable token | `anteroom/ocr.py` | no |
   | classify a drug as high risk | `config/visit_requirements.yaml` | no |
   | severity and which human owns a gap | `anteroom/readiness.py` | no |
   | render a medication dose | `anteroom/brief.py` | no |
   | what a transcript line means | `anteroom/agents.py` | **yes** |
   | phrasing of the consultant brief | `anteroom/brief.py` | **yes** |

   A model writing *"she takes apixaban 5mg twice daily"* in fluent prose is the exact
   failure this system exists to prevent, and no prompt makes that impossible. So the
   model is never given the opportunity.

2. **Strict Pydantic Contracts:**
   - Every tool call adheres to immutable Pydantic schemas:
     - `Confidence` enum: `HIGH`, `MEDIUM`, `LOW`, `UNREADABLE`.
     - `SourceRef`: Strict citation linking (`document_id`, `document_label`, `bounding_box`, `location`).
     - `ExtractedFact`: Usable only if `confidence` is `HIGH` or `MEDIUM` and value is not None.
     - `Medication`: High-risk classification separated from LLM generation.
     - `Gap`: Concrete task with designated role owner (`RECEPTION`, `NURSE`, `DOCTOR`) and call script.
     - `ReadinessReport`: Score (0-100), readiness tier, and role-filtered gap lists.

3. **Tool & Pipeline Modules:**
   - `read_document(path)`: Invokes AWS Textract + Hardware Confidence Gate (`anteroom/ocr.py`).
   - `interpret(doc)`: Strands agent extracting structured facts with evidence spans (`anteroom/agents.py`).
   - `audit(record)`: Deterministic policy evaluation engine (`anteroom/readiness.py`).
   - `compose(facts)`: Pre-visit clinical brief generator citing visual bounding boxes (`anteroom/brief.py`).

### 2.2 Amazon Bedrock & AgentCore Integration

1. **Foundation Models (Amazon Bedrock):**
   - **Primary Extraction & Synthesis:** `us.amazon.nova-lite-v1:0` / `us.amazon.nova-pro-v1:0` via Bedrock. Swappable via `ANTEROOM_MODEL_ID`.
   - **Zero Hallucination Constraint:** The model is passed annotated Textract tokens, *never raw pixels*, completely neutralizing visual dosage guessing.

2. **Amazon Bedrock AgentCore Action Group:**
   - Packaged and dry-run validated under `agentcore/` with OpenAPI 3.0 specification (`agentcore/openapi.json`) and AWS Lambda handler (`agentcore/handler.py`).
   - Exposes three action group operations: `/audit`, `/brief`, and `/reconcile`.

3. **Auditability & Provenance:**
   - Every extracted fact preserves exact source document ID, line number, and normalized bounding box coordinates for real-time visual inspection in the console.

---

## 3. Structural Defense Against Hallucination: The Textract Gate

The single greatest failure mode in medical document AI is a model "helpfully" hallucinating an illegible dose.

```
       [ Smudged Photo: "Apixaban [blur] twice daily" ]
                              │
                              ▼
                 [ AWS Textract OCR Engine ]
                              │
                 Detects Word Bounding Boxes
                 Word: "Apixaban"  Confidence: 99.2%
                 Word: [Blur]      Confidence: 24.1%
                              │
                              ▼
            [ Textract Confidence Gate (Threshold: 60%) ]
                              │
                              ▼
            [ Sanitized Text Fed to Strands Agent ]
            "Apixaban ⟪ILLEGIBLE⟫ twice daily"
                              │
                              ▼
                [ Bedrock LLM Structurer ]
            Physically impossible to invent "5mg"
            because the model never sees the smudge!
                              │
                              ▼
               Result: Confidence = UNREADABLE
               Triggers Nurse Escalation + Call Script
```

* **Why It Wins:** We don't claim "we prompted the model not to guess." We prove the model is **structurally incapable** of guessing because illegibility is detected deterministically by AWS Textract before the LLM ever receives the text.

---

## 4. The Core Clinical IP: Deterministic Policy Engine

The decision layer contains **zero LLM inference**. Whether an appointment can proceed is governed by inspectable clinical policy in `config/visit_requirements.yaml`.

### 4.1 Policy Structure
* **High-Risk Medication Classification:** Hard-coded list (anticoagulants, antiplatelets, insulins, opioids, immunosuppressants, antiarrhythmics). An illegible dose on any of these automatically escalates severity from `IMPORTANT` to `BLOCKING` and assigns the task to a **Nurse** (medicines clarification), never reception.
* **Freshness Windows:** Deterministic date arithmetic:
  - ECG: 180 days (older triggers refresh gap).
  - Renal function: 90 days (older triggers laboratory request).
* **Never Delegate to Reception:** Clinical examination, diagnosis, and management decisions are strictly forbidden from reception routing.

### 4.2 Cross-Document Reconciliation Finding
The agent solves what a single-document summarizer structurally cannot:
1. **Document 2 (Medication list):** `Apixaban [smudge] twice a day` → dose is destroyed.
2. **Document 3 (Discharge screen photo):** *"Apixaban continued. Dose reduced on discharge – see TTO."* → confirms dose was recently altered, but does not state the new dose.
3. **The Agentic Finding:** Anteroom evaluates both documents simultaneously and flags:
   > *"Apixaban was changed according to the discharge summary, but no document in our possession states the current dose. Two independent sources were checked and neither resolves it. Clarify before the consultation."*

---

## 5. User Experience: Streamlit Clinic Console

Instead of a consumer messaging bot (which introduces HIPAA/GDPR concerns for clinics and friction for judges), Anteroom delivers an enterprise-grade **Streamlit Clinic Console** with three distinct role views:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  ANTEROOM │ Ambulatory Intake Coordinator            [Tomorrow's List: Mon 14 Sep 2026] │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  Patient: MARTA RUIZ DELGADO (SYN-0001)   Visit: Cardiology Consult    Status: AT RISK  │
│  Readiness Score: [ 33 / 100 ] ▓▓▓░░░░░░░  (2 Blocking Gaps, 5 Other Gaps)               │
├──────────────────────────┬─────────────────────────────┬────────────────────────────────┤
│ 📋 RECEPTIONIST QUEUE    │ 🩺 NURSE CLARIFICATION      │ 👨‍⚕️ CLINICIAN PRE-VISIT BRIEF   │
│                          │                             │                                │
│ [!] Referral Question    │ [CRITICAL ACTION]           │ Patient: Marta Ruiz Delgado    │
│  - Reason: Missing       │ High-Risk Medication Gap    │ Age: 68F  Cardiology Consult   │
│  - Action: Call referring│ - Drug: Apixaban            │                                │
│    practice Dr. Okafor   │ - Issue: Dose altered on    │ Reason for Visit:              │
│  - Verbatim Phone Script:│   discharge (Doc 3), but    │ [UNRESOLVED] Referral letter   │
│   "Hello, calling from   │   illegible on patient list │ does not state specific query  │
│   Cardiology... letter   │   (Doc 2). Neither gives    │                                │
│   lacks specific query." │   current dose.             │ Active Problem List:           │
│                          │ - Action: Contact hospital  │ • Intermittent palpitations    │
│ [!] Renal Labs (Glare)   │   pharmacy or prescriber.   │   (4 mos, 2-3x/wk) [Doc 1]     │
│  - Action: Request eGFR  │                             │ • Atrial Fibrillation [Doc 3]  │
│    from hospital lab     │ [Mark Reconciled Button]    │                                │
│                          │                             │ Current Medications:           │
│ [Checkbox: Call Done]    │                             │ • Ramipril 5mg daily [Doc 2]   │
│                          │                             │ • Bisoprolol 2.5mg [Doc 2]     │
│                          │                             │ • Apixaban [DOSE UNRESOLVED]   │
├──────────────────────────┴─────────────────────────────┴────────────────────────────────┤
│ 🔍 EVIDENCE & PROVENANCE INSPECTOR                                                      │
│ Click any fact to inspect source bounding box: [Doc 1: Referral] [Doc 2: Meds] [Doc 3]  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│ │  [Image of Document with Bright Green Bounding Box highlighting exact source text]  │ │
│ └─────────────────────────────────────────────────────────────────────────────────────┘ │
│ [ 🚀 TEST YOUR OWN DOCUMENT (Drag & Drop PDF/JPG) ]                                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Test Scenarios & Generalization Protocol

To prove Anteroom is neither a toy demo nor a hard-coded "pessimism machine", the MVP demonstrates three distinct cases:

| Scenario | Patient | Documents | Readiness | What It Proves |
|---|---|---|---|---|
| **Case 1 (Hero)** | Marta Ruiz Delgado | 1. Angled referral letter<br>2. Handwritten meds (smudged Apixaban)<br>3. Monitor screen photo (glare on renal labs) | **33 / 100<br>(AT RISK)** | Interlocking document defects, refusal to guess high-risk drug, role-based task delegation. |
| **Case 2 (Control)** | Thomas Whitfield | 1. Printed GP referral letter<br>2. Complete pharmacy dispensing record<br>3. Normal ECG trace | **100 / 100<br>(READY)** | The agent accurately validates complete records and approves visits without false alarms. |
| **Case 3 (Generalization)** | Tariq Al-Mansoor | 1. International cardiology referral (SI units 88 µmol/L creatinine, DD/MM/YY date conventions) | **88 / 100<br>(NEEDS ACTION)** | **Zero prompt tuning against this format.** Proves model generalizes across regional healthcare conventions. |

---

## 7. Empirical Reliability Benchmark

To substantiate our submission with hard data, we run an empirical hallucination test on Amazon Bedrock:

* **Experiment:** Pass the smudged `02_medication_list.jpg` through the Textract + Bedrock extraction pipeline **20 consecutive times**.
* **Hypothesis:** The pipeline will return `confidence = UNREADABLE` and `dose = None` in 100% of runs.
* **Video Metric:** A dedicated title slide:
  > **"We ran the illegible anticoagulant dose 20 times against Amazon Bedrock. The agent guessed 0 times."**

---

## 8. Role Ownership & 34-Hour Execution Plan

### 8.1 Division of Responsibility
* **Ahmed (Engineering & Infra Lead):**
  - Textract Confidence Gate implementation.
  - Strands Agents SDK orchestration & Bedrock integration.
  - Streamlit Clinic Console with bounding-box viewer.
  - Generalization test runner & 20-run benchmark script.
* **Gerhard (Product & Presentation Lead):**
  - **The 5-Minute Demo Video:** Owns script, screen capture, voiceover, and editing.
  - **Clinical Policy Sanity-Check:** Validates `visit_requirements.yaml` thresholds.
  - **Field Knowledge Input:** Provides non-Western / African referral layout specifications for Case 3.
  - **Devpost Submission Text:** Reviews problem-solution fit narrative.

### 8.2 Hourly Sprint Milestones

```
Sun 13:00 ── Phase 0: AWS Credentials & Bedrock Verification (us-east-1)
Sun 14:30 ── Phase 1: Textract Confidence Gate & Bounding Box Extractor
Sun 17:00 ── Phase 2: Strands Agent Orchestrator & Bedrock Tooling
Sun 18:00 ── Phase 3: Brief Composer with Visual Bounding Box Citations
Sun 21:00 ── Phase 4: Streamlit 3-Role Console Complete & Tested
Mon 09:00 ── Phase 5: Generalization Test (Case 2 Thomas + Case 3 Tariq)
Mon 11:00 ── Phase 6: Run 20x Reliability Benchmark & Log Metrics
Mon 13:00 ── HARD FEATURE FREEZE (Code complete, no new features)
Mon 15:00 ── Phase 7: Video Recording & Editing (Gerhard)
Mon 18:00 ── Phase 8: Devpost Draft Submitted (Buffer against network issues)
Mon 20:00 ── Phase 9: builder.aws.com Bonus Post Published & Final Polish
```

---

## 9. Submission Deliverables Checklist

- [ ] **Public GitHub Repository:** Open source with MIT License visible in About section.
- [ ] **Technical Implementation:** Strands Agents SDK orchestration + AWS Textract + Amazon Bedrock.
- [ ] **Deployment:** Streamlit Live Demo + Bedrock AgentCore deployment configuration.
- [ ] **Documentation:** Comprehensive `README.md` with system architecture diagrams (`mermaid`).
- [ ] **Demo Video (≤ 5 minutes):**
  1. The Pain: Burned appointment slots and fragmented paper/screen intake (0:00 - 0:45).
  2. The Magic: Receptionist photo → Textract gate → Strands agent coordination (0:45 - 2:00).
  3. The Differentiator: Refusal to guess smudged Apixaban + cross-document deduction (2:00 - 3:15).
  4. The 3 Role Queues: Receptionist call script, nurse review, doctor 30s brief (3:15 - 4:15).
  5. Architecture, Reliability Benchmark (20/20 runs), and Impact (4:15 - 5:00).
- [ ] **Bonus Points:** Article published on `builder.aws.com` titled:
  *"Agents for Humans: How We Built Anteroom to Stop Burned Clinic Slots with Strands Agents SDK and Amazon Bedrock"*.

---
*Anteroom is an assistive clinical preparation system. All patient data is synthetic.*
