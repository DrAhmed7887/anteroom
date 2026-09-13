"""The Strands agent layer.

One rule governs this whole module: the model receives text, never pixels. By
the time a transcript reaches an agent here, the confidence gate in ocr.py has
already deleted anything it could not read. The agent's job is semantic -- work
out which line holds the allergies, which token is a drug name -- not to judge
how legible anything was. That judgement was made, numerically, upstream.
"""

from __future__ import annotations

import yaml
from strands import Agent
from strands.models import BedrockModel

from .config import AWS_REGION, MODEL_ID
from .extraction import DocumentExtraction
from .ocr import ILLEGIBLE, OcrDocument
from .readiness import POLICY_PATH

INTERPRETER_PROMPT = f"""\
You convert OCR transcripts of clinical intake documents into structured data
for a clinic's pre-visit check. You are reading a TRANSCRIPT, not an image.

MARKERS IN THE TRANSCRIPT
  {ILLEGIBLE}  The optical character recognition engine could not read this text
            with sufficient confidence, so the text was DELETED before it
            reached you. You have not seen it. Nobody has.
  word⟨?⟩   Read with low confidence. Report the value, it may be imperfect.
  [Lnn]     Line number. Cite it for everything you extract.

YOUR TASK
Return every one of the following that the transcript contains:
  medications  -- EVERY drug named anywhere in the transcript, one entry each,
                  in the order they appear, including any whose dose you cannot
                  read. A drug with an unreadable dose is still a medication and
                  MUST be returned, with dose = null.
  fields       -- EVERY allowed field for which the transcript provides any
                  value at all, even a partial one. Be exhaustive: work down the
                  allowed list one at a time and ask whether the transcript says
                  anything about it. Omitting a field is read downstream as "this
                  document does not contain it", which triggers a phone call to
                  chase information the clinic already has.
  document_kind, notes.

ABSOLUTE RULES
1. Never infer, complete, or supply a value that is not written in the
   transcript. If a dose position holds {ILLEGIBLE}, the dose is null and
   dose_marked_illegible is true. Do not fall back on a typical, standard, or
   most-common dose. A guessed dose is worse than a missing one, because a
   missing dose gets a phone call and a guessed dose gets dispensed.
2. Never merge two medications, and never split one.
3. Extract only fields from the allowed list. If content does not fit, put it
   in notes.
4. Quote values as written. Light normalisation of spacing or capitalisation is
   fine; rewording is not.
5. If the transcript contradicts itself, report both and say so in notes.

You are not diagnosing, triaging, or assessing urgency. You are transcribing
into structure.
"""


def allowed_fields(policy_path=None) -> list[str]:
    """Field vocabulary comes from the clinical policy, so adding a new visit
    type extends extraction without touching this module."""
    policy = yaml.safe_load((policy_path or POLICY_PATH).read_text())
    fields: set[str] = set()
    for key, rules in policy.items():
        if key.startswith("_") or not isinstance(rules, dict):
            continue
        for tier in ("blocking", "important", "minor"):
            fields.update(rules.get(tier) or [])
    return sorted(fields)


def build_model(model_id: str | None = None) -> BedrockModel:
    """temperature=0 because this is transcription, not composition.

    There is no creative latitude wanted here: the same document must yield the
    same structure every time, or a clinic gets a different answer on Tuesday
    than it got on Monday from the identical referral letter. Sampling is a
    feature for prose and a defect for a medical intake record.
    """
    return BedrockModel(
        model_id=model_id or MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
        max_tokens=4096,
    )


def interpreter_agent(model_id: str | None = None) -> Agent:
    return Agent(
        model=build_model(model_id),
        system_prompt=INTERPRETER_PROMPT,
        callback_handler=None,
        name="document_interpreter",
        description="Turns a gated OCR transcript into structured clinical fields.",
    )


def interpret(doc: OcrDocument, model_id: str | None = None,
              agent: Agent | None = None) -> DocumentExtraction:
    """Read one document. The image is never passed -- only the gated transcript."""
    agent = agent or interpreter_agent(model_id)
    prompt = (
        f"Allowed field names: {', '.join(allowed_fields())}\n\n"
        f"Document label: {doc.label}\n"
        f"TRANSCRIPT:\n{doc.annotated_transcript()}"
    )
    result = agent(prompt, structured_output_model=DocumentExtraction)
    return result.structured_output
