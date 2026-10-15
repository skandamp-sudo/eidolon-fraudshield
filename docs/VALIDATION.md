# Scientific evaluation and honest claims

The included model is a **functional dependency-free starter baseline**, not a validated fraud detection solution for use in a bank.

## Current baseline

- Source: seeded, generated PaySim-like toy events, 12,000 rows
- Split: earlier 70% train / next 15% validation / last 15% untouched test (by generation order, time-step grouping approximated)
- Features: log amount, value bands, transaction type, simulated hour — **balance fields and fraud labels excluded**
- Learner: simple standard-library logistic SGD model
- Threshold: selected to maximize F1 on synthetic validation data
- Metrics: see `models/baseline.json`; reports F1, precision, recall, false-positive rate and average precision
- Scoring: 0–100 uncalibrated model score; contribution explanations, not causal attributions

## Separate PaySim temporal pipeline

The original `scripts/train_paysim.py` pipeline uses whole-step chronological partitions, validation-only threshold selection and a 10,001-bin approximation for average precision. It has now completed locally on the canonical 6,362,620-row CSV; [the versioned aggregate report](../benchmarks/paysim-baseline-v1.json) preserves its metrics and provenance. The original artifact remains outside Git. Do not overwrite it by rerunning the original CLI.

The future test is now **previously observed**. Phase 2 uses only original training/validation steps and a protocol frozen before measuring candidate results. Read [the audit](PHASE2_SCIENTIFIC_AUDIT.md) and [reproduction instructions](PHASE2_REPRODUCIBILITY.md). Exact AP on new development windows must not be compared directly with approximate AP from the historical future test. No LinuxONE run or independent real-bank validation has occurred.

## Further scientific work

1. Download and document PaySim dataset version and license/usage terms. It is **synthetic**, not live bank records.
2. Verify the provided CSV's provenance, sorting, expected schema, step coverage and class counts before treating the pipeline output as a benchmark. No model or claim should use label, `isFlaggedFraud`, account ID or **any PaySim balance field** as a predictor.
3. Compare additional models on the identical predeclared steps, fitting transformations on training steps only. Never report a resampled/downsampled evaluation set as if it represented natural fraud prevalence.
4. Add exact PR-AUC and uncertainty analysis if resources permit; preserve the untouched future time window and report fraud-class precision/recall, confusion matrix, false-positive rate and alert volume at the natural base rate.
5. Compare models on identical splits, report decision latency percentiles p50/p95/p99 and throughput, and benchmark on actual IBM LinuxONE hardware.
6. If using the ULB Credit Card Fraud dataset, recognize its anonymized `Time`/`Amount` + PCA features are a **different input schema**. Train a separate adapter/model; do not feed it to the PaySim schema as though equivalent.
7. Observe possible concept drift and feature/schema evolution. Document drift measurements and how the alerts are evaluated by an analyst.

## Red flags to avoid in the judging pitch

- No claim of '99.9% detection', measured fraud savings, 'IBM Z acceleration' or production readiness unless independently measured.
- Do not mix synthetic generator labels into supposed real bank performance results.
- Do not interpret a logistic output as a calibrated fraud probability without calibration on representative data.
- Do not automatically block transactions, and do not store personal account identifiers in a public demo.
