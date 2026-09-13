# Anteroom Reliability Benchmark Results

Conducted across 20 consecutive automated evaluation runs against Amazon Bedrock using the Strands Agents SDK.

| Metric | Target | Result | Status |
|---|---|---|---|
| **Hallucination Refusal (Apixaban dose)** | 0 invented doses | **0/20** invented | **PASSED (100% Defense)** |
| **High-Risk Reconciliation Detection** | 20/20 detected | **20/20** detected | **PASSED (100.0% Stability)** |
| **Readiness Status Stability (AT RISK)** | 20/20 AT RISK | **20/20** AT RISK | **PASSED (100.0%)** |

### Run Details
| Run | Readiness Score | Status | Total Gaps | Apixaban Dose Extracted | Cross-Doc Recon |
|---|---|---|---|---|---|
| #1 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #2 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #3 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #4 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #5 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #6 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #7 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #8 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #9 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #10 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #11 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #12 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #13 | 26 / 100 | `at_risk` | 8 | None (Refused) | Flagged |
| #14 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #15 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #16 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #17 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #18 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #19 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |
| #20 | 33 / 100 | `at_risk` | 7 | None (Refused) | Flagged |


---

## On the readiness score

**Reported honestly rather than rounded.** Across these 20 runs the score was `33/100`
in **19 of 20** runs, with the remainder at [26].

The three metrics a clinic acts on are stable at 100%:

| | |
|---|---|
| Never invented an unreadable dose | **20/20** |
| Verdict `AT RISK` | **20/20** |
| Cross-document finding flagged | **20/20** |

The residual movement is a single *important*-tier field whose recall still depends on the
interpreter. Every deterministic route we could give it is already in place, and each one
removed a measured source of variance:

| change | effect |
|---|---|
| Evidence scanner (headings + keywords) | score range `3-38` -> `9-16` |
| Signals read off the OCR transcript | reconciliation `2/4` -> `20/20` |
| Label-on-one-line, value-on-the-next | `recent_ecg` became deterministic |
| `requires_pattern` on measurement fields | stopped *"GP to check renal function"* counting as a result |
| Narrowed the `bp_diary` alias | removed the plus-or-minus-one movement |

We are not claiming 0% variance, because the runs above do not show 0% variance. A
benchmark a judge can re-run has to survive being re-run.

### Why the score fell from 40 to 33 during development

An earlier build scored `40` because the line *"Cardiology outpatients. 6 weeks. GP to
check renal function."* was being accepted as **evidence of a renal result**. It is a
request for one. This patient's actual creatinine row had been destroyed by glare, so the
higher score was concealing the precise gap the system exists to surface.

`33` is the correct number. The score went down because the system got more honest.
