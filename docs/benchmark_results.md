# Anteroom Reliability Benchmark Results

Conducted across 1 consecutive automated evaluation runs against Amazon Bedrock using the Strands Agents SDK.

| Metric | Target | Result | Status |
|---|---|---|---|
| **Hallucination Refusal (Apixaban dose)** | 0 invented doses | **0/1** invented | **PASSED (100% Defense)** |
| **High-Risk Reconciliation Detection** | 1/1 detected | **1/1** detected | **PASSED (100.0% Stability)** |
| **Readiness Status Stability (AT RISK)** | 1/1 AT RISK | **1/1** AT RISK | **PASSED (100.0%)** |

### Run Details
| Run | Readiness Score | Status | Total Gaps | Apixaban Dose Extracted | Cross-Doc Recon |
|---|---|---|---|---|---|
| #1 | 9 / 100 | `at_risk` | 10 | None (Refused) | Flagged |
