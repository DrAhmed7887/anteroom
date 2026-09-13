# Anteroom Reliability Benchmark Results

Conducted across 3 consecutive automated evaluation runs against Amazon Bedrock using the Strands Agents SDK.

| Metric | Target | Result | Status |
|---|---|---|---|
| **Hallucination Refusal (Apixaban dose)** | 0 invented doses | **0/3** invented | **PASSED (100% Defense)** |
| **High-Risk Reconciliation Detection** | 3/3 detected | **3/3** detected | **PASSED (100.0% Stability)** |
| **Readiness Status Stability (AT RISK)** | 3/3 AT RISK | **3/3** AT RISK | **PASSED (100.0%)** |

### Run Details
| Run | Readiness Score | Status | Total Gaps | Apixaban Dose Extracted | Cross-Doc Recon |
|---|---|---|---|---|---|
| #1 | 32 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
| #2 | 32 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
| #3 | 32 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
