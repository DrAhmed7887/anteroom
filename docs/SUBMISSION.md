# Devpost Submission — Anteroom

**Project Name:** Anteroom — Ambient Clinical Intake Coordinator  
**Tagline:** Checks tomorrow’s clinic list tonight, verifies whether scheduled consultations can actually proceed, and hands reception the exact three calls to make in the morning.  
**Track:** Professional Agents (AWS × Strands Agents SDK Hackathon — "Agents for Humans")  
**Authors:** Dr. Ahmed Zayed (MBBCh, MSc Candidate in Applied Health Informatics at RWTH Aachen; Founder of doctorIQ) & Gerhard  
**Repository:** [https://github.com/DrAhmed7887/anteroom](https://github.com/DrAhmed7887/anteroom)  

---

## 💡 Inspiration

In specialist outpatient clinics, doctors don't lose time simply because electronic health records are long. They lose entire 30-minute consultation slots because intake is fragmented, illegible, or incomplete.

Consider a typical morning in a cardiology clinic:
A patient arrives for an initial consultation. The GP referral letter was photographed with a smartphone at an angle and gives medical history, but omits the actual clinical question. The patient brings a handwritten medication list, but the blood-thinner dose is smudged with ink. A printout of a hospital discharge summary has specular camera glare directly over the recent renal blood test results.

The doctor cannot safely make a management decision without knowing why the patient was referred or what dose of anticoagulant they take. The 30-minute slot becomes an administrative re-booking, clinic capacity is lost, revenue is burned, and the patient waits another four weeks.

As a physician and health informatics researcher, I asked: **Why are doctors triaging paperwork during the consultation, instead of autonomous agents auditing intake the night before?**

---

## 🩺 What It Does

**Anteroom** is an ambient pre-visit intake coordinator built with the **Strands Agents SDK** and deployed on **Amazon Bedrock AgentCore**. It runs the night before clinic, ingesting whatever messy artifacts exist (angled phone photos, handwritten notes, photographed screens), deterministically auditing readiness against clinic policy, and routing actionable work to three role-specific queues before the patient ever arrives:

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
* The **Amazon Bedrock** model (Claude 3.5 Sonnet) is fed the sanitized transcript—it never sees raw blur pixels. It is **physically and structurally incapable** of guessing a dose.

### 2. Strands Agents SDK Orchestration
Using the **Strands Agents SDK**, we implemented an `IntakeCoordinatorAgent` supervisor that manages state transitions:
* Ingests multi-format document bundles.
* Coordinates specialized agents for entity interpretation and deterministic policy auditing.
* Enforces strict Pydantic schemas (`ExtractedFact`, `SourceRef`, `Medication`, `Gap`, `ReadinessReport`).

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

## 🏆 Accomplishments We're Proud Of

1. **Zero Hallucination Guarantee:** In multi-run automated reliability benchmarks against live Amazon Bedrock inference, the model refused to guess the smudged Apixaban dose **100% of the time** (`dose=None`, `confidence=UNREADABLE`).
2. **100% Stable Cross-Document Reconciliation:** Reliably flags altered high-risk medications without false negatives.
3. **Control Case Accuracy:** Tested against clean, well-formatted flatbed-scanned referrals (`apt-002`), achieving **100/100 READY** with zero false positive gaps.
4. **Interactive Streamlit Clinic Console:** A fluid, multi-role UI featuring clickable bounding-box evidence highlights, confidence gate inspection, and role switching.
5. **Comprehensive Automated Test Suite:** 30 unit and integration tests passing in under 1 second.

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
* **Amazon Bedrock** (Claude 3.5 Sonnet)
* **Amazon Textract** (Word-level confidence extraction)
* **Python 3.13**
* **Streamlit** (Clinic Console UI)
* **Pillow (PIL)** (Bounding-box visual proof rendering)
* **Pydantic v2** (Immutable clinical data contracts)
* **Pytest** (Automated verification)
