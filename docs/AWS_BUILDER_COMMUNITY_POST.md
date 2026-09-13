# Agents for Humans: Building Anteroom with Strands Agents SDK and Amazon Bedrock

*By Dr. Ahmed Zayed (MBBCh, MSc Candidate in Applied Health Informatics at RWTH Aachen) & Gerhard*

---

Every clinician has experienced this: you sit down for a 30-minute outpatient consultation, open the patient chart, and discover the referral letter is missing the actual clinical question, the handwritten medication note has an illegible blood-thinner dose, and the photographed screen has glare over the kidney lab results.

You cannot make a safe medical decision without knowing the dose of an anticoagulant. The 30-minute appointment becomes an administrative scramble, clinic capacity is lost, and the patient waits another four weeks.

For the **AWS × Strands Agents SDK Hackathon ("Agents for Humans")**, we built **Anteroom**: an ambient pre-visit intake coordinator that audits tomorrow’s clinic list tonight, verifies whether scheduled appointments can safely proceed, and hands reception the exact three phone calls to make in the morning.

In this article, we share the architectural patterns we developed combining the **Strands Agents SDK**, **Amazon Bedrock**, and **Amazon Textract** to build an agent system that is provably safe for healthcare workflows.

---

## The Core Challenge: LLMs Love to "Helpfully" Guess

When handling messy clinical paperwork, standard LLM applications suffer from a fatal failure mode: **hallucinating illegible text**.

If a patient’s medication note has a smudged line reading `Apixaban [smudge] twice daily`, a multimodal vision model or standard prompt will often attempt to guess a standard dosage (e.g. `5mg twice daily`). In medicine, guessing is unacceptable—the dose might have been `2.5mg` due to renal impairment, or `10mg` in acute treatment.

Prompting an LLM: *"Please do not guess illegible numbers"* is unreliable under distribution shift.

### Our Solution: The Hardware Confidence Gate

Instead of relying on prompt engineering, we implemented a **structural defense**:

```
[ Smudged Photo: "Apixaban [smudge] twice daily" ]
                       │
                       ▼
          [ Amazon Textract OCR ]
          Detects word-level bounding boxes & confidence
          Word: "Apixaban"  Confidence: 99.2%
          Word: [Smudge]    Confidence: 43.1% (<60%)
                       │
                       ▼
     [ Textract Confidence Gate (Threshold: 60%) ]
     Strikes words below 60% and replaces with ⟪ILLEGIBLE⟫
                       │
                       ▼
       [ Sanitized Transcript to Bedrock ]
       "Apixaban ⟪ILLEGIBLE⟫ twice daily"
                       │
                       ▼
       [ Strands Agent on Amazon Bedrock ]
       Extracts: dose=None, confidence=UNREADABLE
```

Because the low-confidence pixels are deleted *before* the language model receives the prompt, the model is **physically and structurally incapable** of guessing the dose. In our 20-run automated reliability benchmark against Amazon Bedrock, the hallucination refusal rate was **100% (0 invented doses across all runs)**.

---

## Orchestration with Strands Agents SDK

We used the **Strands Agents SDK** (`strands-agents`) with strict Pydantic contracts. Two agents, deliberately narrow — a document interpreter and a brief composer — wrapped in deterministic code that makes every safety-critical decision itself:

1. **Document Interpreter (`anteroom/agents.py`):** A Strands agent on Amazon Bedrock (Amazon Nova Lite by default, configured via `ANTEROOM_MODEL_ID`) extracts structured entities — allergies, medications, past history, referral questions — where each fact is bound to its Textract bounding box by the pipeline, not by the model. We kept the model swappable on purpose: the safety guarantee is enforced by the confidence gate and the policy layer around it, so changing the model changes cost and latency, not safety.
2. **Deterministic Readiness Auditor (`anteroom/readiness.py`):** Evaluates extracted facts against clinic policy defined in `visit_requirements.yaml`. No model involved.
3. **Brief Composer (`anteroom/brief.py`):** A Strands agent that synthesizes a 30-second pre-visit briefing narrative for the clinician, citing source lines and bounding boxes. Doses are rendered by code, never by the model.

```python
from strands import Agent
from anteroom.schemas import DocumentExtraction

# Document Interpreter Strands Agent
interpreter = Agent(
    model="us.amazon.nova-lite-v1:0",
    system_prompt="You are a clinical document interpreter. Extract structured entities with strict evidence spans...",
    response_model=DocumentExtraction,
)
```

### Separating Policy from Prediction

A fundamental design principle we followed is: **LLMs handle semantic extraction; deterministic code handles clinical policy.**

Determining whether an intake packet has an acceptable referral question is a semantic task suited to a language model. Determining whether an anticoagulant with an unverified dose blocks consultation is a clinical policy rule that must be 100% deterministic.

By separating the two, our clinical policy engine runs in **0.01 seconds** with zero stochastic variance.

---

## Cross-Document Deduction: The "Hero Moment"

A major advantage of Anteroom's agent architecture is **multi-document reasoning**:
* **Document 1 (Hospital Discharge Summary):** States *"Dose reduced on discharge"*—without specifying the dose.
* **Document 2 (Handwritten Medication List):** Has the Apixaban dose smudged out.

A traditional document-at-a-time tool evaluates both documents as partially complete. Anteroom's coordinator holds both in memory and alerts:
> `[CRITICAL ALERT] Apixaban was changed according to 'Discharge summary', but no document states the current dose. Two independent sources checked; neither resolves it. Clarify before consultation.`

---

## Role-Scoped Action Queues

Clinics don't want a wall of AI text. Anteroom routes tasks to three distinct roles:
1. **Reception Queue:** Missing demographics or referral questions, paired with a **verbatim phone call script** (`☎ "Hello, calling from cardiology before your appointment tomorrow..."`).
2. **Nurse Review:** Medication discrepancy resolution and pharmacy contact.
3. **Doctor Brief:** A 30-second pre-visit summary where every single bullet point links directly to its source bounding box on the original document.

---

## Conclusion & Code

Building AI for healthcare doesn't mean trusting an LLM with patient outcomes. It means using agents for what they do best—understanding human language across messy forms—and wrapping them in rigorous engineering boundaries, hardware confidence gates, and zero-trust authorization.

The complete code, test suite (93 passing unit tests), and Streamlit console are open source on GitHub:
👉 [https://github.com/DrAhmed7887/anteroom](https://github.com/DrAhmed7887/anteroom)
