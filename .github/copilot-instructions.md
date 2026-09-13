# GitHub Copilot Repository Instructions — Anteroom

## Project Overview
Anteroom is an ambient clinical intake coordinator for outpatient clinics built for the AWS "Agents for Humans" Hackathon (Professional Agents track).
It audits messy intake materials (angled paper referrals, handwritten medication lists, photographed monitor screens) against clinical policy to ensure appointments are clinically and administratively prepared before the patient arrives.

## Architecture & Technology Stack
- **Language:** Python 3.13+
- **OCR & Confidence Gating:** Amazon Textract (`DetectDocumentText`). Words with confidence below threshold (<60%) are replaced with `⟪ILLEGIBLE⟫` before any model sees them.
- **LLM & Orchestration:** Strands Agents SDK + Amazon Bedrock (`anthropic.claude-3-5-sonnet` / Amazon Nova).
- **Decision Engine:** Deterministic policy engine (`anteroom/readiness.py` + `config/visit_requirements.yaml`). **Zero LLM inference in the decision loop.**
- **Contracts:** Strict Pydantic models (`anteroom/schemas.py`).
- **UI:** Streamlit 3-panel Clinic Console (Reception, Nurse, Doctor).

## Core Clinical & Safety Conventions
1. **`UNREADABLE` is a First-Class State:**
   - Never collapse unreadable or low-confidence fields to `None` or infer standard therapeutic dosing.
   - An illegible dose on a high-risk medication must ALWAYS yield `confidence=Confidence.UNREADABLE` and `dose=None`, triggering an escalation gap.
2. **Policy-Owned Risk Classification:**
   - The model must NEVER rate how dangerous a drug is. High-risk medications are mapped strictly in `config/visit_requirements.yaml`.
3. **Cross-Document Reconciliation:**
   - Look for change language (e.g. "dose reduced on discharge") in document transcripts. If an altered drug lacks a legible dose on patient medication lists, flag an unresolved cross-document discrepancy.
4. **Role Routing:**
   - High-risk medication gaps route to `Role.NURSE`.
   - Missing administrative fields route to `Role.RECEPTION` with verbatim `call_script` generation.
   - Usable facts compile into `Role.DOCTOR` pre-visit brief.

## Testing & Verification Commands
- **Run all unit tests:**
  ```bash
  PYTHONPATH=. pytest -q
  ```
- **Run targeted readiness test:**
  ```bash
  PYTHONPATH=. pytest -q tests/test_readiness.py::test_marta_is_at_risk
  ```
- **Run clean control patient test:**
  ```bash
  PYTHONPATH=. pytest -q tests/test_clean_patient.py
  ```
- **Run determinism verification loop:**
  ```bash
  PYTHONPATH=. python scripts/check_determinism.py 4
  ```
