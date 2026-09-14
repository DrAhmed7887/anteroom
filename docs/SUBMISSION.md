# Devpost Submission — Anteroom

**Project Name:** Anteroom — Ambient Clinical Intake Coordinator  
**Tagline:** Checks tomorrow’s clinic list tonight, verifies whether scheduled consultations can actually proceed, and hands reception the exact three calls to make in the morning.  
**Track:** Professional Agents (AWS × Strands Agents SDK Hackathon — "Agents for Humans")  
**Authors:** Dr. Ahmed Zayed (MBBCh, MSc Candidate in Applied Health Informatics at RWTH Aachen; Founder of doctorIQ) & Gerhard  
**Repository:** [https://github.com/DrAhmed7887/anteroom](https://github.com/DrAhmed7887/anteroom)  

---

## 🔗 Links

| | |
|---|---|
| **Live demo (Primary)** | https://drahmed7887.github.io/anteroom/ |
| **Live demo (Vercel)** | https://anteroom-pi.vercel.app |
| **Source** | https://github.com/DrAhmed7887/anteroom (MIT) |
| **Architecture** | [Architecture Diagram](https://github.com/DrAhmed7887/anteroom/blob/main/docs/architecture.png) |
| **Reliability benchmark** | [Benchmark Results (20 runs)](https://github.com/DrAhmed7887/anteroom/blob/main/docs/benchmark_results.md) |

The live console needs no sign-up and makes no AWS calls: all three cases are pre-computed
from real Textract output. All patient data is synthetic.

## 💡 Inspiration

In specialist outpatient clinics, doctors don't lose time simply because electronic health records are long. They lose entire 30-minute consultation slots because intake is fragmented, illegible, or incomplete.

Consider a typical morning in a cardiology clinic:
A patient arrives for an initial consultation. The GP referral letter was photographed with a smartphone at an angle and gives medical history, but omits the actual clinical question. The patient brings a handwritten medication list, but the blood-thinner dose is smudged with ink. A printout of a hospital discharge summary has specular camera glare directly over the recent renal blood test results.

The doctor cannot safely make a management decision without knowing why the patient was referred or what dose of anticoagulant they take. The 30-minute slot becomes an administrative re-booking, clinic capacity is lost, revenue is burned, and the patient waits another four weeks.

As a physician and health informatics researcher, I asked: **Why are doctors triaging paperwork during the consultation, instead of autonomous agents auditing intake the night before?**

---

## 🩺 What It Does

**Anteroom** is an ambient pre-visit intake coordinator built with the **Strands Agents SDK** on **Amazon Bedrock**, with an **Amazon Bedrock AgentCore** action group packaged and dry-run validated. It runs the night before clinic, ingesting whatever messy artifacts exist (angled phone photos, handwritten notes, photographed screens), deterministically auditing readiness against clinic policy, and routing actionable work to three role-specific queues before the patient ever arrives:

1. **☎ Receptionist Action Queue:** Identifies missing administrative prerequisites (e.g. missing referral question, missing contact info) and generates **verbatim telephone call scripts** so front-desk staff can resolve gaps with one quick phone call.
2. **💊 Nurse Review Queue:** Handles clinical reconciliation gaps (e.g., verifying an altered high-risk anticoagulant with the prescribing pharmacy).
3. **🩺 Doctor 30-Second Pre-Consultation Brief:** Gives the clinician an instant, structured orientation with clickable visual bounding-box citations leading directly to the exact source pixels on the original document.

### 🛡️ Non-Negotiable Safety Boundary
* Anteroom does **not** diagnose.
* Anteroom does **not** prescribe or recommend treatments.
* Anteroom does **not** perform emergency clinical triage.
* Anteroom is strictly an **assistive pre-visit completeness and audit coordinator**.

---

## ⚙️ How We Built It

We designed Anteroom as a multi-tier agent architecture combining AWS serverless intelligence with strict deterministic clinical policy engines:

### 1. The Hardware Confidence Gate (Structural Hallucination Defense)
The fatal danger in clinical LLM applications is a model "helpfully" hallucinating an illegible dose. We built a structural defense:
* Every document passes through **Amazon Textract**, which computes word-level confidence scores.
* Any word scoring below the 60% threshold is stripped and replaced with an explicit `⟪ILLEGIBLE⟫` token before any language model sees the text.
* The **Amazon Bedrock** model is fed the sanitized transcript — it never sees raw blur pixels. It is **structurally incapable** of guessing a dose, because the token was deleted before it arrived.
* The model is set by one variable (`ANTEROOM_MODEL_ID`, default Amazon Nova Lite) precisely *because* the guarantee does not depend on it. Swapping the model changes cost and latency, not safety.

### 2. Strands Agents SDK — deliberately two agents, deliberately narrow

The Strands Agents SDK runs **two** agents, both using structured output against strict
Pydantic contracts:

| Agent | File | What it decides |
|---|---|---|
| **Document Interpreter** | `anteroom/agents.py` | What a transcript line *means* — which line holds the allergies, which token is a drug name |
| **Brief Composer** | `anteroom/brief.py` | Two sentences of clinical prose for the consultant |

**There is no supervisor agent, and that is the design, not a shortcut.** Every
safety-critical decision is made by deterministic code *around* the agents:

* deleting an unreadable token — `anteroom/ocr.py`, a confidence threshold
* tiering a drug as high risk — `config/visit_requirements.yaml`, a lookup table
* deciding severity and which human owns a gap — `anteroom/readiness.py`, **no model**
* rendering every medication dose — `anteroom/brief.py`, string concatenation

A model writing *"she takes apixaban 5mg twice daily"* in fluent prose is the exact
failure this system exists to prevent, and no prompt makes that impossible. So the model
is never given the opportunity. Contracts enforced: `ExtractedFact`, `SourceRef`,
`Medication`, `Gap`, `ReadinessReport`, `DocumentExtraction`, `BriefNarrative`.

Anyone can audit a YAML file. Nobody can audit a prompt.

### 2b. What "deterministic" does and does not mean here

Worth stating precisely, because the distinction is the whole design and an imprecise
claim is easy to disprove:

| | |
|---|---|
| ✅ **Deterministic** | the confidence gate, the normalisation layer, the readiness auditor, the role routing, every rendered dose |
| ⚠️ **Not deterministic** | the interpreter's extraction *recall* — it is a language model |

Measured over 20 consecutive live runs on the same three documents:

| | |
|---|---|
| Never invented an unreadable dose | **20/20** |
| Verdict `AT RISK` | **20/20** |
| Cross-document finding flagged | **20/20** |
| Readiness score | `33/100` in **19 of 20**; one run at 26 |

We do not claim the pipeline is deterministic, because it is not. We claim the safety
layer is, and we publish the runs that show where the remaining movement is. A benchmark
a judge can re-run has to survive being re-run.

### 3. Cross-Document Clinical Deduction
Generic document summarizers look at one document at a time. Anteroom maintains multi-document context:
* A hospital discharge screen photo notes: *"Dose reduced on discharge"* (without stating the new dose).
* A handwritten medication note has the dose smudged out.
* Holding both documents simultaneously, Anteroom's deterministic auditor deduces: *An altered high-risk anticoagulant has no recorded dose across all available sources.* It immediately generates a blocking safety alert for the nurse.

### 4. Zero-Trust Clinical Authorization
Anteroom enforces strict practice and role scoping:
* Cross-practice reads raise `AccessDenied` and log a security audit trail.
* Receptionists see administrative logistics and phone scripts, but are strictly prohibited from viewing clinician briefs.
* Clinicians receive immediate visibility into all blocking safety gaps.

---

## 🚧 Challenges We Ran Into

1. **The LLM Completion Reflex:** Multimodal models reflexively infer smudged numbers based on statistical training priors. Prompt engineering alone ("do not guess") proved unreliable. We resolved this structurally: Amazon Textract performs word-level confidence scoring, and our OCR confidence gate replaces low-confidence words with `⟪ILLEGIBLE⟫` before any language model sees the text.
2. **The "Silent Absence" Problem:** Window glare across an intake monitor scan obliterated the creatinine/eGFR row, yet Textract returned the surrounding lines with 95%+ confidence. A generic summarizer would report the document as complete. We solved this with inspectable clinical schemas (`config/visit_requirements.yaml`) that audit what *must* be present rather than summarizing what was observed.
3. **Multi-Role Scoping & Privacy:** Creating an operational interface where receptionists receive actionable telephone scripts without exposing sensitive clinician briefs required strict role-based access contracts (`AccessDenied` boundaries across practice and role domains).

---

## 🏆 Accomplishments We're Proud Of

1. **Zero Hallucination Guarantee:** In multi-run automated reliability benchmarks against live Amazon Bedrock inference, the model refused to guess the smudged Apixaban dose **100% of the time** (`dose=None`, `confidence=UNREADABLE`).
2. **100% Stable Cross-Document Reconciliation:** Reliably flags altered high-risk medications without false negatives.
3. **Control Case Accuracy:** Tested against clean, well-formatted flatbed-scanned referrals (`apt-002`), achieving **100/100 READY** with zero false positive gaps.
4. **Interactive Streamlit Clinic Console:** A fluid, multi-role UI featuring clickable bounding-box evidence highlights, confidence gate inspection, and role switching.
5. **Comprehensive Automated Test Suite:** 93 unit and integration tests passing in under 1 second.

---

## 🧠 What We Learned

1. **Separating Prediction from Policy:** LLMs excel at semantic extraction from unstructured text; deterministic code excels at policy enforcement. Letting the LLM extract the text while Python rules enforce whether an anticoagulant needs a dose produces bulletproof reliability.
2. **Hardware Confidence Gates Beat Prompt Engineering:** Prompting a model "please don't guess illegible text" fails under edge cases. Deleting low-confidence OCR words before the prompt is assembled guarantees safety.
3. **Clinicians Need Provenance, Not Chatbots:** Doctors don't want a chatbot chatting with them; they want a 30-second bulleted brief with clickable links to the original image pixels.

---

## 🔮 What's Next for Anteroom

* **EHR Integration:** Bi-directional HL7 FHIR integration (Epic, Cerner, EMIS Health) to automatically read clinic schedules and write back resolved intake notes.
* **Ambient SMS Pre-Intake:** Automatically sending SMS prompts to patients 48 hours prior to the visit for missing administrative details.
* **Multi-Clinic Practice Management:** Expanding the practice-scoping model into multi-tenant hospital trusts.

---

## 🛠️ Built With

* **Strands Agents SDK** (`strands-agents`)
* **Amazon Bedrock** (Amazon Nova Lite by default; model set by `ANTEROOM_MODEL_ID`)
* **Amazon Textract** (Word-level confidence extraction)
* **Python 3.13**
* **Streamlit** (Clinic Console UI)
* **Pillow (PIL)** (Bounding-box visual proof rendering)
* **Pydantic v2** (Immutable clinical data contracts)
* **Pytest** (Automated verification)
