"""Runtime configuration.

The model is behind one variable on purpose. Anteroom's safety property -- that
an unreadable dose can never become a guessed one -- is enforced by the
confidence gate in ocr.py and the policy in readiness.py, both of which run
outside the model. So the model is swappable without weakening anything, and
we can prove that by running the suite against more than one.
"""

from __future__ import annotations

import os

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Amazon Nova Lite by default. The structuring task is deliberately narrow --
# the hard guarantees live in the confidence gate and the policy layer -- so a
# small model is sufficient, and in testing Nova Lite emitted proper JSON nulls
# where Nova Pro emitted the string "null". Override with ANTEROOM_MODEL_ID.
MODEL_ID = os.getenv("ANTEROOM_MODEL_ID", "us.amazon.nova-lite-v1:0")

ALTERNATE_MODELS = {
    "nova-pro": "us.amazon.nova-pro-v1:0",
    "nova-lite": "us.amazon.nova-lite-v1:0",
    "sonnet-5": "global.anthropic.claude-sonnet-5",
    "haiku-4-5": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
}
