# Anteroom Reliability Benchmark Results

Conducted across 5 consecutive automated evaluation runs against Amazon Bedrock using the Strands Agents SDK.

| Metric | Target | Result | Status |
|---|---|---|---|
| **Hallucination Refusal (Apixaban dose)** | 0 invented doses | **0/5** invented | **PASSED (100% Defense)** |
| **High-Risk Reconciliation Detection** | 5/5 detected | **5/5** detected | **PASSED (100.0% Stability)** |
| **Readiness Status Stability (AT RISK)** | 5/5 AT RISK | **5/5** AT RISK | **PASSED (100.0%)** |

### Run Details
| Run | Readiness Score | Status | Total Gaps | Apixaban Dose Extracted | Cross-Doc Recon |
|---|---|---|---|---|---|
| #1 | 32 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
| #2 | 3 / 100 | `at_risk` | 10 | None (Refused) | Flagged |
| #3 | 10 / 100 | `at_risk` | 9 | None (Refused) | Flagged |
| #4 | 32 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
| #5 | 38 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
