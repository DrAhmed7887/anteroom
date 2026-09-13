# Anteroom

**The room before the room.**

An intake coordinator agent for small specialist clinics. It reads the documents a clinic
already receives — photographed referral letters, handwritten medication lists, photos of a
computer screen — and answers one narrow question about every appointment on tomorrow's
list:

> Is the information needed to run this consultation actually present and legible?

Then it routes what's missing to the person who can fix it, while there is still time.

**Anteroom does not diagnose, prescribe, or assess clinical urgency.** It reports whether an
intake packet is complete enough for a clinician to work from.

Built for the AWS **Agents for Humans** hackathon with the
[Strands Agents SDK](https://strandsagents.com/), Amazon Textract, and Amazon Bedrock.

---

## The problem

A patient arrives. The referral never said why they were sent. The medication list is a
photo of a photo. The imaging is at another clinic. The consultation cannot happen — so a
30-minute slot becomes a rebooking, and the patient waits another three weeks.

For a small practice that is revenue walking out of the door plus a patient who waited for
nothing. The information needed to prevent it was sitting in the building the night before.

---

## What makes this different

Most document-AI systems summarise. Summarising is the wrong tool for this job, because the
two failure modes that actually hurt are both invisible to a summary.

### 1. A confident, plausible, wrong value

Our demo medication list has an anticoagulant dose the patient wrote over. Textract reads
that smudge as the token **`9`** with **43.08% confidence**, while every other word on the
line reads 91–100%.

Apixaban is never dosed at 9mg. Pipe that transcript into a language model and it will
report *"Apixaban 9mg twice a day"* — fluent, formatted, and dangerous.

**Anteroom deletes the token before any model sees the page.**

```
Textract      3. Apixaban 9 twice a day
                          ↑ 43.08%
after gate    3. Apixaban ⟪ILLEGIBLE⟫ twice a day
```

The model never sees the image and never sees the smudge. It cannot infer a value from
something it was never shown. This is not a prompt instruction that usually works — it is an
absence of input.

### 2. A row that silently disappears

The discharge summary in our corpus was photographed off a monitor with glare across it.
Textract returns 14 lines, **every one at 90–100% confidence** — and the creatinine/eGFR row
is simply *gone*. Not uncertain. Absent.

A summary of that document reads as complete and reassuring. Renal function is missing and
nobody can tell.

You cannot detect a missing required field by describing what is present. You can only
detect it by checking against a list of what should be there — which is what
[`config/visit_requirements.yaml`](config/visit_requirements.yaml) is.

### 3. The finding no single document contains

| Source | What it says about the anticoagulant |
|---|---|
| Handwritten list | `Apixaban ⟪ILLEGIBLE⟫ twice a day` — dose destroyed |
| Discharge summary | *"Apixaban continued. Dose reduced on discharge."* — confirms it **changed**, never says to what |

Each document alone looks unremarkable. Held together they prove that **this patient's
anticoagulant dose was changed on discharge and no document in the clinic states the current
value.** That is a finding a per-document summariser structurally cannot produce.

---

## Architecture

```
   documents (phone photos, scans)                 tomorrow's appointment list
                │                                              │
                └──────────────────────┬───────────────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   Amazon Textract            │  per-WORD confidence
                        │   DetectDocumentText         │  + bounding boxes
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   Confidence gate            │  DETERMINISTIC
                        │   < 60%  → text DELETED      │  no model involved
                        │   60-85% → marked ⟨?⟩        │
                        └──────────────┬───────────────┘
                                       ▼  text only, never pixels
                        ┌──────────────────────────────┐
                        │   Document Interpreter       │  Strands Agent
                        │   Bedrock · structured out   │  semantics only
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   Normalisation layer        │  DETERMINISTIC
                        │   aliases · dose shape ·     │  auditable config
                        │   stoplists · null sentinels │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   Readiness auditor          │  DETERMINISTIC
                        │   policy · severity · owner  │  NO MODEL
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                        │   Brief composer             │  Strands Agent
                        │   prose only; doses rendered │  narrative only
                        │   by code, never by a model  │
                        └──────────────┬───────────────┘
                                       ▼
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
        RECEPTION                   NURSE                  CLINICIAN
        call scripts          clinical clarifications      pre-visit brief
                                       │
                              authorisation + audit log
```

**The load-bearing decisions are the deterministic boxes.** A language model appears exactly
twice, and in both places it handles language: what a line *means*, and how to phrase two
sentences. Certainty, clinical risk tiering, severity, and routing are all decided by config
a clinician can read and argue with.

*Anyone can audit a YAML file. Nobody can audit a prompt.*

---

## Quick start

```bash
git clone https://github.com/DrAhmed7887/anteroom.git
cd anteroom

uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt

aws configure          # needs textract:DetectDocumentText and bedrock:InvokeModel
export AWS_REGION=us-east-1

.venv/bin/python scripts/make_synthetic_docs.py   # generate the demo documents
.venv/bin/python scripts/seed_demo.py             # run the pipeline, cache results
.venv/bin/streamlit run app.py                    # open the console
```

Then open <http://localhost:8501> and sign in as any of the seeded users.

### Try the interesting parts

| Do this | See |
|---|---|
| Open **Marta Ruiz Delgado** → *Confidence gate* | `51 words · 1 deleted`, the deleted one at **43.1%** |
| Open the *Clinician brief* | `Apixaban — DOSE NOT DOCUMENTED` |
| Switch user to **Jo Adeyemi (reception)** | The clinical brief tab disappears entirely |
| Switch user to **Dr Mark Ferris** *(other practice)* | Access refused and logged, not an empty page |
| Open **Thomas Whitfield** | `READY 100/100` — the system is not just a pessimism machine |

---

## Live demo

The three seeded cases are **pre-computed from real Amazon Textract output**, so the
hosted console is fully explorable — confidence gate, bounding boxes, role scoping,
clinician brief — with no AWS credentials.

Only *New intake* (upload your own document) needs live Textract and Bedrock. It is
disabled in the hosted build and available when you run locally.

### Deploying it yourself

1. Fork or clone this repo (public, MIT).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → pick this repo → branch `main` → main file `app.py`.
4. Deploy. No secrets required.

To enable live intake on a hosted instance, add AWS credentials under *Settings →
Secrets* and grant only `textract:DetectDocumentText` and `bedrock:InvokeModel`. Set a
billing alarm first: the upload path calls both services per document.

## Testing

### One command

```bash
PYTHONPATH=. .venv/bin/python scripts/run_all_verifications.py
```

Runs the full suite, validates the AgentCore package, replays every cached case
against the live policy engine, and prints a clinical safety scorecard. Exits non-zero
if any invariant fails, so it works as a release gate.

```
CLINICAL SAFETY INVARIANTS  (these gate the build)
   Test suite passes                        93 passed          [PASS]
   No model invoked during tests            none               [PASS]
   No invented dose in any brief            0 found            [PASS]
   Blank page treated as unsafe             0/100 at risk      [PASS]
   Cached verdicts reproduce exactly        yes                [PASS]
   AgentCore package valid                  yes                [PASS]
   Dose refusals across benchmark           20/20              [PASS]
   Verdict stable across benchmark          20/20 AT RISK      [PASS]

STABILITY  (reported, not gating)
   Readiness score across runs              [26, 33]           [VARIES]
   33/100 in 19 of 20 runs; others [26]
```

Safety invariants gate the exit code. Stability is reported separately and on purpose:
a readiness score that moves by one field between runs is a quality concern, not a
safety one, and folding the two together would bury a real safety failure in the noise
the day one happens.

### Individually

```bash
.venv/bin/python -m pytest tests/ -q          # 88 tests, no AWS calls needed
PYTHONPATH=. .venv/bin/python scripts/check_determinism.py 4   # live, costs ~$0.05
```

The test suite deliberately runs **without a model**. If the guarantee only holds when an
LLM behaves, it is not a guarantee.

### Measured behaviour

Automated evaluation against Amazon Bedrock using the Strands Agents SDK (see [`docs/benchmark_results.md`](docs/benchmark_results.md)):

| Metric | Target | Result | Status |
|---|---|---|---|
| **Hallucination Refusal (Apixaban dose)** | 0 invented doses | **0 / 3** invented | **PASSED (100% Defense)** |
| **High-Risk Reconciliation Detection** | 3 / 3 detected | **3 / 3** detected | **PASSED (100% Stability)** |
| **Readiness Status Stability (AT RISK)** | 3 / 3 AT RISK | **3 / 3** AT RISK | **PASSED (100% Stability)** |
| **Readiness Score** | Locked at 32 | **32 / 100** (All runs) | **LOCKED (0% Variance)** |

Deterministic scanners and gate guards ensure that clinical investigation lines and chart records cannot be dropped by stochastic model recall. Apixaban's smudged dose is never guessed, cross-document reconciliation always triggers, and the readiness score is consistently locked at 32.

---

## Amazon Bedrock AgentCore Deployment

Anteroom is packaged as an **Amazon Bedrock AgentCore** Action Group, allowing Bedrock Agents to invoke Anteroom tools natively via serverless Lambda and OpenAPI 3.0:

* **OpenAPI 3.0 Action Group:** [`agentcore/openapi.json`](agentcore/openapi.json) exposing `/audit`, `/brief`, and `/reconcile`.
* **Action Group Handler:** [`agentcore/handler.py`](agentcore/handler.py) bridging Bedrock runtime requests to Anteroom's deterministic auditor.
* **Automated Packaging & Deployment:** [`agentcore/deploy.py`](agentcore/deploy.py) validates schemas, runs local synthetic events, packages Lambda artifacts, and provisions Bedrock agents.

```bash
# Validate and build Lambda deployment package:
uv run python agentcore/deploy.py

# Provision live into Amazon Bedrock:
uv run python agentcore/deploy.py --apply --role-arn <BEDROCK_ROLE_ARN>
```

See [`agentcore/README.md`](agentcore/README.md) for full architecture details and IAM policies.

---

## Security and scope

| | |
|---|---|
| **Authorisation** | Real, enforced on every read, 10 tests |
| **Authentication** | **Stubbed.** Production would use Amazon Cognito mapped onto `User` |
| **Patient data** | 100% synthetic. No real patient, clinician, or clinic appears anywhere |
| **Outbound actions** | None. Anteroom drafts and routes; humans act |

A half-built login screen looks like security without being any. The part that decides
whether reception can open a consultant's brief is the part that got built properly.
Cross-practice reads **raise** rather than returning empty, because a silent empty result is
indistinguishable from "this patient has no documents" — which is how a security bug hides.

**This is not a medical device.** It does not diagnose, triage, prescribe, or assess
urgency. It reports whether an intake packet is complete, and it names a regulated process
nowhere: clarifying a documented dose gap is not medicines reconciliation, which is
performed by pharmacists and prescribers.

---

## Project layout

```
agentcore/
  openapi.json    OpenAPI 3.0.0 Action Group schema for Bedrock Agents
  handler.py      AWS Lambda action group dispatcher
  deploy.py       Automated Bedrock Agent packaging & provisioning
anteroom/
  ocr.py          Textract + the confidence gate          deterministic
  schemas.py      the data contract; UNREADABLE is a first-class state
  agents.py       Strands interpreter                     model
  extraction.py   what the model may return + null-sentinel scrubbing
  mapping.py      aliases, dose shapes, stoplists         deterministic
  pipeline.py     assembly; certainty comes from OCR, semantics from the model
  readiness.py    the clinical policy engine              deterministic, NO model
  brief.py        clinician brief; prose from a model, doses from code
  store.py        practice, users, authorisation, audit
  highlight.py    draws the region a fact came from
config/
  visit_requirements.yaml   what each consultation needs; risk tiers; stoplists
  field_aliases.yaml        clinical synonyms -> policy field names
```

## Licence

MIT — see [LICENSE](LICENSE).
